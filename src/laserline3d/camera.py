"""USB camera acquisition isolated in a dedicated Qt thread."""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from typing import Any

import cv2
from PySide6.QtCore import QThread, Signal


BACKENDS: dict[str, int] = {
    "DirectShow (recommended)": cv2.CAP_DSHOW,
    "Media Foundation": cv2.CAP_MSMF,
    "Automatic": cv2.CAP_ANY,
}


@dataclass(slots=True)
class CameraRequest:
    index: int = 0
    backend: int = cv2.CAP_DSHOW
    width: int = 1280
    height: int = 720
    fps: float = 30.0
    pixel_format: str | None = None


class CameraWorker(QThread):
    frame_ready = Signal(object, float, int)
    camera_opened = Signal(object)
    properties_reported = Signal(object)
    properties_applied = Signal(object)
    camera_error = Signal(str)
    camera_closed = Signal()

    def __init__(self, request: CameraRequest) -> None:
        super().__init__()
        self.request = request
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._property_requests: list[tuple[str, dict[str, float]]] = []
        self._show_settings = False
        self._report_properties = False

    def request_stop(self) -> None:
        self._stop.set()

    def set_camera_property(self, property_id: int, value: float) -> None:
        names = {identifier: name for name, identifier in camera_property_ids().items()}
        name = names.get(int(property_id))
        if name is None:
            raise ValueError(f"Unknown OpenCV camera property ID: {property_id}")
        self.apply_camera_properties(
            f"legacy-{time.monotonic_ns()}", {name: float(value)}
        )

    def apply_camera_properties(
        self, operation_id: str, properties: dict[str, float]
    ) -> None:
        """Queue one named control batch for driver apply and read-back."""

        requested = {str(name): float(value) for name, value in properties.items()}
        with self._lock:
            self._property_requests.append((str(operation_id), requested))

    def open_native_settings(self) -> None:
        with self._lock:
            self._show_settings = True

    def request_property_snapshot(self) -> None:
        with self._lock:
            self._report_properties = True

    def run(self) -> None:
        capture = cv2.VideoCapture(self.request.index, self.request.backend)
        try:
            if not capture.isOpened():
                self.camera_error.emit(
                    f"Could not open camera {self.request.index}. Close other camera apps and try another backend."
                )
                return
            set_results: dict[str, bool] = {}
            if self.request.pixel_format:
                set_results["pixel_format"] = bool(
                    capture.set(
                        cv2.CAP_PROP_FOURCC,
                        cv2.VideoWriter_fourcc(*self.request.pixel_format),
                    )
                )
            set_results["width"] = bool(
                capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.request.width)
            )
            set_results["height"] = bool(
                capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.request.height)
            )
            set_results["fps"] = bool(capture.set(cv2.CAP_PROP_FPS, self.request.fps))
            reported_properties = read_camera_properties(capture)
            actual_width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
            actual_fps = float(capture.get(cv2.CAP_PROP_FPS))
            actual_format = decode_fourcc(
                float(reported_properties.get("Video FourCC") or 0.0)
            )
            actual = {
                "index": self.request.index,
                "backend": capture.getBackendName() if hasattr(capture, "getBackendName") else str(self.request.backend),
                "width": actual_width,
                "height": actual_height,
                "fps": actual_fps,
                "pixel_format": actual_format,
                "properties": reported_properties,
                "property_evidence": describe_camera_properties(reported_properties),
                "mode_negotiation": assess_camera_mode(
                    self.request,
                    actual_width=actual_width,
                    actual_height=actual_height,
                    actual_fps=actual_fps,
                    actual_format=actual_format,
                    set_results=set_results,
                ),
            }
            self.camera_opened.emit(actual)
            self.properties_reported.emit(reported_properties)
            sequence = 0
            failures = 0
            while not self._stop.is_set():
                with self._lock:
                    property_requests = self._property_requests
                    self._property_requests = []
                    show_settings = self._show_settings
                    self._show_settings = False
                    report_properties = self._report_properties
                    self._report_properties = False
                for operation_id, properties in property_requests:
                    applied = apply_camera_property_batch(capture, properties)
                    applied["operation_id"] = operation_id
                    applied["properties"] = read_camera_properties(capture)
                    self.properties_applied.emit(applied)
                if show_settings:
                    capture.set(cv2.CAP_PROP_SETTINGS, 0)
                    report_properties = True
                if report_properties:
                    self.properties_reported.emit(read_camera_properties(capture))
                ok, frame = capture.read()
                if not ok or frame is None:
                    failures += 1
                    if failures >= 20:
                        self.camera_error.emit(
                            "Camera stopped delivering frames. Check the USB connection."
                        )
                        break
                    self.msleep(20)
                    continue
                failures = 0
                self.frame_ready.emit(frame, time.monotonic(), sequence)
                sequence += 1
        except Exception as error:
            self.camera_error.emit(f"Camera failure: {error}")
        finally:
            capture.release()
            self.camera_closed.emit()


def camera_property_ids() -> dict[str, int]:
    return {
        "Auto exposure": cv2.CAP_PROP_AUTO_EXPOSURE,
        "Exposure": cv2.CAP_PROP_EXPOSURE,
        "Gain": cv2.CAP_PROP_GAIN,
        "Brightness": cv2.CAP_PROP_BRIGHTNESS,
        "Contrast": cv2.CAP_PROP_CONTRAST,
        "Saturation": cv2.CAP_PROP_SATURATION,
        "Hue": cv2.CAP_PROP_HUE,
        "Gamma": cv2.CAP_PROP_GAMMA,
        "Sharpness": cv2.CAP_PROP_SHARPNESS,
        "Backlight compensation": cv2.CAP_PROP_BACKLIGHT,
        "Autofocus": cv2.CAP_PROP_AUTOFOCUS,
        "Focus": cv2.CAP_PROP_FOCUS,
        "Auto white balance": cv2.CAP_PROP_AUTO_WB,
        "White balance temperature": cv2.CAP_PROP_WB_TEMPERATURE,
        "Sensor temperature": cv2.CAP_PROP_TEMPERATURE,
        "Iris": cv2.CAP_PROP_IRIS,
        "Zoom": cv2.CAP_PROP_ZOOM,
        "Video FourCC": cv2.CAP_PROP_FOURCC,
        "Capture buffer size": cv2.CAP_PROP_BUFFERSIZE,
    }


CAMERA_CONTROLLABLE_PROPERTIES: tuple[str, ...] = (
    "Autofocus",
    "Focus",
    "Auto exposure",
    "Exposure",
    "Gain",
    "Brightness",
    "Contrast",
    "Saturation",
    "Hue",
    "Gamma",
    "Sharpness",
    "Backlight compensation",
    "Auto white balance",
    "White balance temperature",
    "Iris",
    "Zoom",
)


def apply_camera_property_batch(
    capture: Any, properties: dict[str, float]
) -> dict[str, object]:
    """Apply selected controls and report the driver's actual values.

    Camera property ranges and supported controls are driver-specific. This
    deliberately makes no generic range assumptions and treats read-back as
    the evidence, including when ``set`` returns false.
    """

    identifiers = camera_property_ids()
    results: dict[str, dict[str, object]] = {}
    for name, raw_value in properties.items():
        if name not in CAMERA_CONTROLLABLE_PROPERTIES or name not in identifiers:
            results[name] = {
                "requested": raw_value,
                "actual": None,
                "set_returned": None,
                "matches": None,
                "status": "not_writable",
            }
            continue
        requested = float(raw_value)
        property_id = identifiers[name]
        before = _read_property_value(capture, property_id)
        set_failure: str | None = None
        try:
            set_returned = bool(capture.set(property_id, requested))
        except Exception as error:  # Driver/backend failures vary by platform.
            set_returned = False
            set_failure = type(error).__name__
        actual = _read_property_value(capture, property_id)
        matches = (
            actual is not None
            and math.isclose(
                actual,
                requested,
                rel_tol=1e-4,
                abs_tol=max(1e-6, abs(requested) * 1e-4),
            )
        )
        if matches:
            status = "applied" if set_returned else "matched_despite_set_refusal"
        elif actual is None:
            status = "unreported"
        elif set_returned:
            status = "substituted"
        else:
            status = "refused"
        item: dict[str, object] = {
            "requested": requested,
            "before": before,
            "actual": actual,
            "set_returned": set_returned,
            "matches": matches if actual is not None else None,
            "status": status,
        }
        if set_failure is not None:
            item["failure_type"] = set_failure
        results[name] = item
    statuses = {str(item["status"]) for item in results.values()}
    matched = sum(bool(item.get("matches")) for item in results.values())
    if results and matched == len(results):
        outcome = "applied"
    elif matched:
        outcome = "partial"
    elif statuses == {"substituted"}:
        outcome = "substituted"
    else:
        outcome = "failed"
    return {"result": outcome, "requested_count": len(properties), "results": results}


def _read_property_value(capture: Any, property_id: int) -> float | None:
    try:
        value = float(capture.get(property_id))
    except Exception:  # Driver/backend failures vary by platform.
        return None
    return value if math.isfinite(value) else None


def assess_camera_mode(
    request: CameraRequest,
    *,
    actual_width: int,
    actual_height: int,
    actual_fps: float,
    actual_format: str | None,
    set_results: dict[str, bool] | None = None,
) -> dict[str, object]:
    """Describe what the driver accepted without claiming unsupported modes.

    UVC mode enumeration is not consistently exposed through OpenCV. The
    reliable cross-camera check is to request a mode and read back the mode the
    backend actually opened. Frame rates such as 29.97 are treated as matching
    a 30 fps request.
    """

    mismatches: dict[str, dict[str, object]] = {}
    unverified: list[str] = []
    if (actual_width, actual_height) != (request.width, request.height):
        mismatches["resolution"] = {
            "requested": [int(request.width), int(request.height)],
            "actual": [int(actual_width), int(actual_height)],
        }
    if math.isfinite(actual_fps) and actual_fps > 0:
        tolerance = max(0.5, abs(float(request.fps)) * 0.03)
        if abs(actual_fps - float(request.fps)) > tolerance:
            mismatches["fps"] = {
                "requested": float(request.fps),
                "actual": float(actual_fps),
            }
    else:
        unverified.append("fps")
    if request.pixel_format:
        if not actual_format:
            unverified.append("pixel_format")
        elif request.pixel_format != actual_format:
            mismatches["pixel_format"] = {
                "requested": request.pixel_format,
                "actual": actual_format,
            }
    return {
        "requested": {
            "resolution": [int(request.width), int(request.height)],
            "fps": float(request.fps),
            "pixel_format": request.pixel_format or "driver_default",
        },
        "actual": {
            "resolution": [int(actual_width), int(actual_height)],
            "fps": float(actual_fps) if math.isfinite(actual_fps) else None,
            "pixel_format": actual_format or "unreported",
        },
        "set_results": dict(set_results or {}),
        "mismatches": mismatches,
        "unverified": unverified,
        "accepted": not mismatches and not unverified,
    }


def read_camera_properties(capture: Any) -> dict[str, float | None]:
    """Read raw driver values without claiming that zero means supported/off.

    OpenCV camera-property availability and ranges depend on the selected
    backend, driver, and camera. The native settings dialog remains the safe
    place to change them; this snapshot is diagnostic evidence only.
    """

    values: dict[str, float | None] = {}
    for name, property_id in camera_property_ids().items():
        try:
            value = float(capture.get(property_id))
        except (AttributeError, TypeError, ValueError, cv2.error):
            value = None
        values[name] = value
    return values


def camera_property_value_status(value: object) -> str:
    """Classify a raw OpenCV property value without overstating support.

    OpenCV specifies ``0`` as the usual value returned for an unsupported
    property, but zero is also legitimate for controls such as gain and hue.
    Non-finite values and read failures are unambiguously unavailable; zero is
    deliberately labelled ambiguous rather than incorrectly called supported.
    """

    if value is None:
        return "unavailable"
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "unavailable"
    if not math.isfinite(numeric):
        return "unavailable"
    if numeric == 0.0:
        return "zero_or_unsupported"
    return "reported"


def describe_camera_properties(
    properties: dict[str, float | None],
) -> dict[str, dict[str, object]]:
    """Add property IDs and support caveats to a raw driver snapshot."""

    identifiers = camera_property_ids()
    evidence: dict[str, dict[str, object]] = {}
    for name, property_id in identifiers.items():
        value = properties.get(name)
        item: dict[str, object] = {
            "property_id": int(property_id),
            "raw_value": value if value is not None and math.isfinite(value) else None,
            "status": camera_property_value_status(value),
        }
        if name == "Video FourCC" and item["status"] == "reported":
            item["decoded_fourcc"] = decode_fourcc(float(value))
        evidence[name] = item
    return evidence


def decode_fourcc(value: float) -> str | None:
    """Decode a numeric FourCC when it contains four printable ASCII bytes."""

    if not math.isfinite(value) or value <= 0:
        return None
    integer = int(round(value))
    decoded = "".join(chr((integer >> (8 * offset)) & 0xFF) for offset in range(4))
    return decoded if all(32 <= ord(character) <= 126 for character in decoded) else None
