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
    camera_error = Signal(str)
    camera_closed = Signal()

    def __init__(self, request: CameraRequest) -> None:
        super().__init__()
        self.request = request
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._properties: dict[int, float] = {}
        self._show_settings = False
        self._report_properties = False

    def request_stop(self) -> None:
        self._stop.set()

    def set_camera_property(self, property_id: int, value: float) -> None:
        with self._lock:
            self._properties[int(property_id)] = float(value)

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
                    properties = self._properties
                    self._properties = {}
                    show_settings = self._show_settings
                    self._show_settings = False
                    report_properties = self._report_properties
                    self._report_properties = False
                for property_id, value in properties.items():
                    capture.set(property_id, value)
                if show_settings:
                    capture.set(cv2.CAP_PROP_SETTINGS, 0)
                    report_properties = True
                if properties:
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
