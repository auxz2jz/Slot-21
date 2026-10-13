"""Typed data carried between calibration, capture, reconstruction, and export."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

import numpy as np
from numpy.typing import NDArray


FloatArray = NDArray[np.float64]
UInt8Array = NDArray[np.uint8]


def _created_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _array(value: Any, shape: tuple[int, ...] | None = None) -> FloatArray:
    result = np.asarray(value, dtype=np.float64)
    if shape is not None and result.shape != shape:
        raise ValueError(f"Expected array shape {shape}, got {result.shape}")
    if not np.all(np.isfinite(result)):
        raise ValueError("Calibration contains a non-finite number")
    return result


@dataclass(slots=True)
class CameraCalibration:
    camera_matrix: FloatArray
    distortion: FloatArray
    image_size: tuple[int, int]
    rms_error: float
    board_inner_corners: tuple[int, int] = (9, 6)
    square_size_mm: float = 25.0
    accepted_views: int = 0
    mean_reprojection_error_px: float = 0.0
    created_utc: str = field(default_factory=_created_now)

    def __post_init__(self) -> None:
        self.camera_matrix = _array(self.camera_matrix, (3, 3))
        self.distortion = _array(self.distortion).reshape(-1)
        self.image_size = (int(self.image_size[0]), int(self.image_size[1]))
        if self.image_size[0] <= 0 or self.image_size[1] <= 0:
            raise ValueError("Image size must be positive")
        if self.camera_matrix[0, 0] <= 0 or self.camera_matrix[1, 1] <= 0:
            raise ValueError("Camera focal lengths must be positive")
        if self.square_size_mm <= 0:
            raise ValueError("Chessboard square size must be positive")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "laserline3d.camera_calibration.v1",
            "camera_matrix": self.camera_matrix.tolist(),
            "distortion": self.distortion.tolist(),
            "image_size": list(self.image_size),
            "rms_error": float(self.rms_error),
            "board_inner_corners": list(self.board_inner_corners),
            "square_size_mm": float(self.square_size_mm),
            "accepted_views": int(self.accepted_views),
            "mean_reprojection_error_px": float(self.mean_reprojection_error_px),
            "created_utc": self.created_utc,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CameraCalibration":
        return cls(
            camera_matrix=data["camera_matrix"],
            distortion=data.get("distortion", []),
            image_size=tuple(data["image_size"]),
            rms_error=float(data.get("rms_error", 0.0)),
            board_inner_corners=tuple(data.get("board_inner_corners", (9, 6))),
            square_size_mm=float(data.get("square_size_mm", 25.0)),
            accepted_views=int(data.get("accepted_views", 0)),
            mean_reprojection_error_px=float(
                data.get("mean_reprojection_error_px", 0.0)
            ),
            created_utc=str(data.get("created_utc", _created_now())),
        )


@dataclass(slots=True)
class CornerCalibration:
    """Pose and measured geometry of the two-panel reference corner.

    World coordinates use millimetres. The vertical hinge is X=Z=0, Y points
    upward, and both wings open toward +Z. ``rvec`` and ``tvec`` transform a
    world point into OpenCV camera coordinates.
    """

    rvec: FloatArray
    tvec: FloatArray
    wing_width_mm: float
    height_mm: float
    hinge_angle_deg: float
    image_points: FloatArray
    object_roi: tuple[int, int, int, int]
    pose_reprojection_error_px: float = 0.0
    created_utc: str = field(default_factory=_created_now)

    def __post_init__(self) -> None:
        self.rvec = _array(self.rvec).reshape(3)
        self.tvec = _array(self.tvec).reshape(3)
        self.image_points = _array(self.image_points, (6, 2))
        self.object_roi = tuple(int(v) for v in self.object_roi)
        if self.wing_width_mm <= 0 or self.height_mm <= 0:
            raise ValueError("Corner width and height must be positive")
        if not 30.0 <= self.hinge_angle_deg <= 150.0:
            raise ValueError("Corner angle must be between 30 and 150 degrees")
        if self.object_roi[2] <= 0 or self.object_roi[3] <= 0:
            raise ValueError("Object area must have positive width and height")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "laserline3d.corner_calibration.v1",
            "rvec": self.rvec.tolist(),
            "tvec": self.tvec.tolist(),
            "wing_width_mm": float(self.wing_width_mm),
            "height_mm": float(self.height_mm),
            "hinge_angle_deg": float(self.hinge_angle_deg),
            "image_points": self.image_points.tolist(),
            "object_roi": list(self.object_roi),
            "pose_reprojection_error_px": float(self.pose_reprojection_error_px),
            "created_utc": self.created_utc,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CornerCalibration":
        return cls(
            rvec=data["rvec"],
            tvec=data["tvec"],
            wing_width_mm=float(data["wing_width_mm"]),
            height_mm=float(data["height_mm"]),
            hinge_angle_deg=float(data.get("hinge_angle_deg", 90.0)),
            image_points=data["image_points"],
            object_roi=tuple(data["object_roi"]),
            pose_reprojection_error_px=float(
                data.get("pose_reprojection_error_px", 0.0)
            ),
            created_utc=str(data.get("created_utc", _created_now())),
        )


@dataclass(slots=True)
class LaserSettings:
    minimum_red: int = 120
    minimum_dominance: int = 45
    threshold: float = 55.0
    ridge_half_width_px: int = 2
    minimum_component_px: int = 8
    orientation: str = "horizontal"
    use_background: bool = True

    def __post_init__(self) -> None:
        self.minimum_red = int(np.clip(self.minimum_red, 0, 255))
        self.minimum_dominance = int(np.clip(self.minimum_dominance, 0, 255))
        self.threshold = float(max(0.0, self.threshold))
        self.ridge_half_width_px = int(np.clip(self.ridge_half_width_px, 1, 8))
        self.minimum_component_px = int(max(1, self.minimum_component_px))
        if self.orientation not in {"horizontal", "vertical", "auto"}:
            raise ValueError("Laser orientation must be horizontal, vertical, or auto")


@dataclass(slots=True)
class ScanSettings:
    min_reference_points_per_wall: int = 12
    ransac_distance_mm: float = 1.5
    max_plane_rms_mm: float = 2.0
    min_depth_mm: float = 50.0
    max_depth_mm: float = 3000.0
    voxel_size_mm: float = 0.75
    max_points: int = 2_000_000
    capture_interval_ms: int = 80


@dataclass(slots=True)
class ScanProfile:
    points_world: FloatArray
    colors_rgb: UInt8Array
    image_points: FloatArray
    frame_index: int
    timestamp_s: float
    laser_plane_camera: FloatArray
    plane_rms_mm: float
    left_reference_count: int
    right_reference_count: int

    def __post_init__(self) -> None:
        self.points_world = _array(self.points_world).reshape(-1, 3)
        self.image_points = _array(self.image_points).reshape(-1, 2)
        self.colors_rgb = np.asarray(self.colors_rgb, dtype=np.uint8).reshape(-1, 3)
        self.laser_plane_camera = _array(self.laser_plane_camera).reshape(4)
        count = len(self.points_world)
        if len(self.image_points) != count or len(self.colors_rgb) != count:
            raise ValueError("Profile point, colour, and image arrays must align")


@dataclass(slots=True)
class PointCloud:
    points: FloatArray = field(
        default_factory=lambda: np.empty((0, 3), dtype=np.float64)
    )
    colors: UInt8Array = field(
        default_factory=lambda: np.empty((0, 3), dtype=np.uint8)
    )
    image_points: FloatArray = field(
        default_factory=lambda: np.empty((0, 2), dtype=np.float64)
    )

    def __post_init__(self) -> None:
        self.points = _array(self.points).reshape(-1, 3)
        self.colors = np.asarray(self.colors, dtype=np.uint8).reshape(-1, 3)
        self.image_points = _array(self.image_points).reshape(-1, 2)
        if not (len(self.points) == len(self.colors) == len(self.image_points)):
            raise ValueError("Point-cloud arrays must have equal lengths")

    @classmethod
    def from_profiles(cls, profiles: list[ScanProfile]) -> "PointCloud":
        if not profiles:
            return cls()
        return cls(
            points=np.concatenate([p.points_world for p in profiles]),
            colors=np.concatenate([p.colors_rgb for p in profiles]),
            image_points=np.concatenate([p.image_points for p in profiles]),
        )

    @property
    def bounds(self) -> tuple[FloatArray, FloatArray] | None:
        if not len(self.points):
            return None
        return self.points.min(axis=0), self.points.max(axis=0)


@dataclass(slots=True)
class Mesh:
    vertices: FloatArray
    faces: NDArray[np.int32]
    colors: UInt8Array

    def __post_init__(self) -> None:
        self.vertices = _array(self.vertices).reshape(-1, 3)
        self.faces = np.asarray(self.faces, dtype=np.int32).reshape(-1, 3)
        self.colors = np.asarray(self.colors, dtype=np.uint8).reshape(-1, 3)
        if len(self.vertices) != len(self.colors):
            raise ValueError("Every mesh vertex must have a colour")
        if len(self.faces) and (
            self.faces.min() < 0 or self.faces.max() >= len(self.vertices)
        ):
            raise ValueError("Mesh face index is outside the vertex array")


def settings_dict(value: LaserSettings | ScanSettings) -> dict[str, Any]:
    return asdict(value)
