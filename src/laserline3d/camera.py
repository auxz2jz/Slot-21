"""USB camera acquisition isolated in a dedicated Qt thread."""

from __future__ import annotations

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
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.request.width)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.request.height)
            capture.set(cv2.CAP_PROP_FPS, self.request.fps)
            reported_properties = read_camera_properties(capture)
            actual = {
                "index": self.request.index,
                "backend": capture.getBackendName() if hasattr(capture, "getBackendName") else str(self.request.backend),
                "width": int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)),
                "height": int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                "fps": float(capture.get(cv2.CAP_PROP_FPS)),
                "properties": reported_properties,
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
        "Sharpness": cv2.CAP_PROP_SHARPNESS,
        "Autofocus": cv2.CAP_PROP_AUTOFOCUS,
        "Focus": cv2.CAP_PROP_FOCUS,
        "Auto white balance": cv2.CAP_PROP_AUTO_WB,
        "White balance temperature": cv2.CAP_PROP_WB_TEMPERATURE,
        "Zoom": cv2.CAP_PROP_ZOOM,
    }


def read_camera_properties(capture: Any) -> dict[str, float]:
    """Read raw driver values without claiming that zero means supported/off.

    OpenCV camera-property availability and ranges depend on the selected
    backend, driver, and camera. The native settings dialog remains the safe
    place to change them; this snapshot is diagnostic evidence only.
    """

    return {
        name: float(capture.get(property_id))
        for name, property_id in camera_property_ids().items()
    }
