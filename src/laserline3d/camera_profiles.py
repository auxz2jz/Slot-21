"""Versioned, portable camera-control profile storage."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .calibration import save_json_atomic
from .camera import CAMERA_CONTROLLABLE_PROPERTIES, CameraRequest


CAMERA_PROFILE_SCHEMA = "laserline3d.camera-profile"
CAMERA_PROFILE_VERSION = 1
SUPPORTED_PIXEL_FORMATS = {None, "MJPG", "YUY2"}


@dataclass(slots=True)
class CameraProfile:
    """Requested camera mode plus explicitly selected UVC control values."""

    name: str
    camera: CameraRequest
    properties: dict[str, float] = field(default_factory=dict)

    def validate(self) -> None:
        self.name = str(self.name).strip()
        if not self.name:
            raise ValueError("Profile name cannot be empty")
        if len(self.name) > 120:
            raise ValueError("Profile name must be 120 characters or fewer")
        if isinstance(self.camera.index, bool) or not 0 <= int(self.camera.index) <= 15:
            raise ValueError("Camera number must be between 0 and 15")
        if isinstance(self.camera.backend, bool) or not isinstance(self.camera.backend, int):
            raise ValueError("Camera backend must be an integer OpenCV backend ID")
        if int(self.camera.width) <= 0 or int(self.camera.height) <= 0:
            raise ValueError("Camera resolution must be positive")
        fps = float(self.camera.fps)
        if not math.isfinite(fps) or not 1.0 <= fps <= 120.0:
            raise ValueError("Requested frame rate must be between 1 and 120")
        if self.camera.pixel_format not in SUPPORTED_PIXEL_FORMATS:
            raise ValueError("USB video format must be MJPG, YUY2, or driver default")
        allowed = set(CAMERA_CONTROLLABLE_PROPERTIES)
        normalized: dict[str, float] = {}
        for raw_name, raw_value in self.properties.items():
            name = str(raw_name)
            if name not in allowed:
                raise ValueError(f"Camera property is not writable by this application: {name}")
            if isinstance(raw_value, bool):
                raise ValueError(f"Camera property {name} must be a numeric driver value")
            value = float(raw_value)
            if not math.isfinite(value):
                raise ValueError(f"Camera property {name} must be finite")
            normalized[name] = value
        self.properties = normalized

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema": CAMERA_PROFILE_SCHEMA,
            "schema_version": CAMERA_PROFILE_VERSION,
            "name": self.name,
            "camera": {
                "index": int(self.camera.index),
                "backend": int(self.camera.backend),
                "width": int(self.camera.width),
                "height": int(self.camera.height),
                "fps": float(self.camera.fps),
                "pixel_format": self.camera.pixel_format,
            },
            "properties": dict(self.properties),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CameraProfile":
        if not isinstance(data, dict):
            raise ValueError("Camera profile must be a JSON object")
        if data.get("schema") != CAMERA_PROFILE_SCHEMA:
            raise ValueError("This is not a LaserLine3D camera profile")
        if data.get("schema_version") != CAMERA_PROFILE_VERSION:
            raise ValueError(
                f"Unsupported camera profile version: {data.get('schema_version')!r}"
            )
        camera_data = data.get("camera")
        properties = data.get("properties", {})
        if not isinstance(camera_data, dict):
            raise ValueError("Camera profile is missing its camera mode")
        if not isinstance(properties, dict):
            raise ValueError("Camera profile properties must be a JSON object")
        required = ("index", "backend", "width", "height", "fps")
        missing = [name for name in required if name not in camera_data]
        if missing:
            raise ValueError(f"Camera profile is missing: {', '.join(missing)}")
        try:
            request = CameraRequest(
                index=int(camera_data["index"]),
                backend=int(camera_data["backend"]),
                width=int(camera_data["width"]),
                height=int(camera_data["height"]),
                fps=float(camera_data["fps"]),
                pixel_format=camera_data.get("pixel_format"),
            )
        except (TypeError, ValueError) as error:
            raise ValueError(f"Camera profile has an invalid camera mode: {error}") from error
        profile = cls(
            name=str(data.get("name", "")),
            camera=request,
            properties=dict(properties),
        )
        profile.validate()
        return profile


def save_camera_profile(path: Path, profile: CameraProfile) -> None:
    save_json_atomic(Path(path), profile.to_dict())


def load_camera_profile(path: Path) -> CameraProfile:
    try:
        with Path(path).open("r", encoding="utf-8") as stream:
            data = json.load(stream)
    except json.JSONDecodeError as error:
        raise ValueError(f"Camera profile is not valid JSON: {error.msg}") from error
    return CameraProfile.from_dict(data)
