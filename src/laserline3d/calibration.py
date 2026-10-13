"""Camera-lens calibration and JSON profile storage."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from numpy.typing import NDArray

from .models import CameraCalibration, CornerCalibration


@dataclass(slots=True)
class CalibrationCapture:
    image_points: NDArray[np.float32]
    image_size: tuple[int, int]
    sharpness: float
    centroid: tuple[float, float]
    coverage: float


@dataclass(slots=True)
class ChessboardCalibrator:
    inner_corners: tuple[int, int] = (9, 6)
    square_size_mm: float = 25.0
    captures: list[CalibrationCapture] = field(default_factory=list)

    def detect(
        self, frame_bgr: NDArray[np.uint8]
    ) -> tuple[bool, NDArray[np.float32] | None, dict[str, float]]:
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        flags = cv2.CALIB_CB_EXHAUSTIVE | cv2.CALIB_CB_ACCURACY
        found, corners = cv2.findChessboardCornersSB(gray, self.inner_corners, flags)
        sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        metrics = {"sharpness": sharpness, "coverage": 0.0}
        if not found or corners is None:
            return False, None, metrics
        corners = corners.astype(np.float32).reshape(-1, 1, 2)
        hull = cv2.convexHull(corners)
        coverage = float(cv2.contourArea(hull) / (gray.shape[0] * gray.shape[1]))
        metrics["coverage"] = coverage
        return True, corners, metrics

    def add_frame(
        self, frame_bgr: NDArray[np.uint8], minimum_sharpness: float = 35.0
    ) -> tuple[bool, str, NDArray[np.float32] | None]:
        found, corners, metrics = self.detect(frame_bgr)
        if not found or corners is None:
            return False, "Chessboard was not found", None
        if metrics["sharpness"] < minimum_sharpness:
            return False, "Image is blurry; hold the board still", corners
        height, width = frame_bgr.shape[:2]
        image_size = (width, height)
        if self.captures and image_size != self.captures[0].image_size:
            return False, "Resolution changed during calibration", corners
        center = tuple(np.mean(corners.reshape(-1, 2), axis=0).tolist())
        diagonal = float(np.hypot(width, height))
        for existing in self.captures:
            center_distance = float(np.linalg.norm(np.asarray(center) - existing.centroid))
            coverage_delta = abs(metrics["coverage"] - existing.coverage)
            if center_distance < 0.025 * diagonal and coverage_delta < 0.015:
                return False, "View is too similar to one already captured", corners
        self.captures.append(
            CalibrationCapture(
                image_points=corners,
                image_size=image_size,
                sharpness=metrics["sharpness"],
                centroid=center,
                coverage=metrics["coverage"],
            )
        )
        return True, f"Accepted view {len(self.captures)}", corners

    def calibrate(self, minimum_views: int = 10) -> CameraCalibration:
        if len(self.captures) < minimum_views:
            raise ValueError(
                f"Capture at least {minimum_views} different chessboard views"
            )
        width, height = self.inner_corners
        object_template = np.zeros((width * height, 3), np.float32)
        object_template[:, :2] = np.mgrid[0:width, 0:height].T.reshape(-1, 2)
        object_template *= float(self.square_size_mm)
        object_points = [object_template.copy() for _ in self.captures]
        image_points = [capture.image_points for capture in self.captures]
        image_size = self.captures[0].image_size
        flags = cv2.CALIB_RATIONAL_MODEL
        rms, matrix, distortion, rvecs, tvecs = cv2.calibrateCamera(
            object_points, image_points, image_size, None, None, flags=flags
        )
        errors: list[float] = []
        for world, observed, rvec, tvec in zip(
            object_points, image_points, rvecs, tvecs, strict=True
        ):
            projected, _ = cv2.projectPoints(
                world, rvec, tvec, matrix, distortion
            )
            delta = projected.reshape(-1, 2) - observed.reshape(-1, 2)
            errors.append(float(np.sqrt(np.mean(np.sum(delta * delta, axis=1)))))
        return CameraCalibration(
            camera_matrix=matrix,
            distortion=distortion.reshape(-1),
            image_size=image_size,
            rms_error=float(rms),
            board_inner_corners=self.inner_corners,
            square_size_mm=self.square_size_mm,
            accepted_views=len(self.captures),
            mean_reprojection_error_px=float(np.mean(errors)),
        )


def save_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def load_camera_calibration(path: Path) -> CameraCalibration:
    with Path(path).open("r", encoding="utf-8") as handle:
        return CameraCalibration.from_dict(json.load(handle))


def save_camera_calibration(path: Path, calibration: CameraCalibration) -> None:
    save_json_atomic(path, calibration.to_dict())


def load_corner_calibration(path: Path) -> CornerCalibration:
    with Path(path).open("r", encoding="utf-8") as handle:
        return CornerCalibration.from_dict(json.load(handle))


def save_corner_calibration(path: Path, calibration: CornerCalibration) -> None:
    save_json_atomic(path, calibration.to_dict())
