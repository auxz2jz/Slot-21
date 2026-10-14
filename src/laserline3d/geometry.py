"""Camera rays, reference-corner geometry, laser plane fitting, and transforms."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
from numpy.typing import NDArray

from .models import CameraCalibration, CornerCalibration, FloatArray


EPSILON = 1e-9
MIN_PLANE_SUPPORT_RATIO = 0.003


def corner_landmarks(
    wing_width_mm: float, height_mm: float, angle_deg: float = 90.0
) -> FloatArray:
    """Return six landmark coordinates in UI click order.

    Order: left outer top, left outer bottom, hinge top, hinge bottom,
    right outer top, right outer bottom.
    """
    half = np.deg2rad(angle_deg / 2.0)
    x = wing_width_mm * np.sin(half)
    z = wing_width_mm * np.cos(half)
    return np.asarray(
        [
            [-x, height_mm, z],
            [-x, 0.0, z],
            [0.0, height_mm, 0.0],
            [0.0, 0.0, 0.0],
            [x, height_mm, z],
            [x, 0.0, z],
        ],
        dtype=np.float64,
    )


def wall_polygons_world(corner: CornerCalibration) -> tuple[FloatArray, FloatArray]:
    pts = corner_landmarks(
        corner.wing_width_mm, corner.height_mm, corner.hinge_angle_deg
    )
    left = pts[[0, 1, 3, 2]]
    right = pts[[2, 3, 5, 4]]
    return left, right


def fit_corner_pose(
    image_points: NDArray[np.floating],
    camera: CameraCalibration,
    wing_width_mm: float,
    height_mm: float,
    angle_deg: float = 90.0,
) -> CornerCalibration:
    image = np.asarray(image_points, dtype=np.float64).reshape(6, 2)
    world = corner_landmarks(wing_width_mm, height_mm, angle_deg)
    ok, rvec, tvec = cv2.solvePnP(
        world,
        image,
        camera.camera_matrix,
        camera.distortion,
        flags=cv2.SOLVEPNP_ITERATIVE,
    )
    if not ok:
        raise RuntimeError("OpenCV could not solve the reference-corner pose")
    projected, _ = cv2.projectPoints(
        world, rvec, tvec, camera.camera_matrix, camera.distortion
    )
    projected = projected.reshape(-1, 2)
    error = float(np.sqrt(np.mean(np.sum((projected - image) ** 2, axis=1))))
    x0, y0 = np.min(image, axis=0)
    x1, y1 = np.max(image, axis=0)
    roi_width = max(20, int((x1 - x0) * 0.45))
    roi_height = max(20, int((y1 - y0) * 0.80))
    roi_x = int((x0 + x1 - roi_width) / 2)
    roi_y = int((y0 + y1 - roi_height) / 2)
    return CornerCalibration(
        rvec=rvec.reshape(3),
        tvec=tvec.reshape(3),
        wing_width_mm=wing_width_mm,
        height_mm=height_mm,
        hinge_angle_deg=angle_deg,
        image_points=image,
        object_roi=(roi_x, roi_y, roi_width, roi_height),
        pose_reprojection_error_px=error,
    )


def rotation_matrix(rvec: NDArray[np.floating]) -> FloatArray:
    matrix, _ = cv2.Rodrigues(np.asarray(rvec, dtype=np.float64).reshape(3, 1))
    return matrix


def transform_world_to_camera(
    points: NDArray[np.floating], corner: CornerCalibration
) -> FloatArray:
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    rot = rotation_matrix(corner.rvec)
    return (rot @ pts.T).T + corner.tvec


def transform_camera_to_world(
    points: NDArray[np.floating], corner: CornerCalibration
) -> FloatArray:
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    rot = rotation_matrix(corner.rvec)
    return (rot.T @ (pts - corner.tvec).T).T


def world_plane_to_camera(
    plane_world: NDArray[np.floating], corner: CornerCalibration
) -> FloatArray:
    plane = np.asarray(plane_world, dtype=np.float64).reshape(4)
    normal_world, offset_world = plane[:3], plane[3]
    rot = rotation_matrix(corner.rvec)
    normal_camera = rot @ normal_world
    offset_camera = float(offset_world - normal_camera @ corner.tvec)
    scale = np.linalg.norm(normal_camera)
    return np.r_[normal_camera / scale, offset_camera / scale]


def corner_wall_planes_world(
    angle_deg: float = 90.0,
) -> tuple[FloatArray, FloatArray]:
    half = np.deg2rad(angle_deg / 2.0)
    # Left wing contains direction (-sin(a), 0, cos(a)); right is mirrored.
    left_normal = np.array([np.cos(half), 0.0, np.sin(half)])
    right_normal = np.array([-np.cos(half), 0.0, np.sin(half)])
    return np.r_[left_normal, 0.0], np.r_[right_normal, 0.0]


def image_points_to_rays(
    image_points: NDArray[np.floating], camera: CameraCalibration
) -> FloatArray:
    points = np.asarray(image_points, dtype=np.float64).reshape(-1, 1, 2)
    normalized = cv2.undistortPoints(
        points, camera.camera_matrix, camera.distortion
    ).reshape(-1, 2)
    rays = np.column_stack((normalized, np.ones(len(normalized))))
    norms = np.linalg.norm(rays, axis=1, keepdims=True)
    return rays / np.maximum(norms, EPSILON)


def intersect_rays_with_plane(
    rays: NDArray[np.floating], plane: NDArray[np.floating]
) -> tuple[FloatArray, NDArray[np.bool_]]:
    direction = np.asarray(rays, dtype=np.float64).reshape(-1, 3)
    coeff = np.asarray(plane, dtype=np.float64).reshape(4)
    denom = direction @ coeff[:3]
    valid = np.abs(denom) > EPSILON
    distance = np.full(len(direction), np.nan, dtype=np.float64)
    distance[valid] = -coeff[3] / denom[valid]
    valid &= distance > 0.0
    points = direction * distance[:, None]
    return points, valid


def fit_plane_svd(points: NDArray[np.floating]) -> tuple[FloatArray, float]:
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    if len(pts) < 3:
        raise ValueError("At least three points are required to fit a plane")
    centroid = pts.mean(axis=0)
    _, _, vh = np.linalg.svd(pts - centroid, full_matrices=False)
    normal = vh[-1]
    normal /= np.linalg.norm(normal)
    offset = -float(normal @ centroid)
    distances = np.abs(pts @ normal + offset)
    return np.r_[normal, offset], float(np.sqrt(np.mean(distances**2)))


@dataclass(slots=True)
class PlaneFit:
    plane: FloatArray
    rms_mm: float
    inliers: NDArray[np.bool_]
    support_ratio: float
    normal_uncertainty_deg: float
    evidence: "PlaneFitEvidence | None" = None


@dataclass(frozen=True, slots=True)
class PlaneFitEvidence:
    """JSON-safe evidence describing a laser-plane fit attempt.

    The evidence is intentionally retained when a fit is rejected.  This lets
    support bundles distinguish a genuinely noisy line from reference samples
    that are nearly collinear and therefore cannot define a unique plane.
    """

    reference_point_count: int
    left_reference_count: int
    right_reference_count: int
    iterations_attempted: int
    valid_model_count: int
    inlier_count: int = 0
    left_inlier_count: int = 0
    right_inlier_count: int = 0
    rms_mm: float | None = None
    median_residual_mm: float | None = None
    support_ratio: float | None = None
    covariance_eigenvalues_mm2: tuple[float, float, float] | None = None
    left_inlier_span_mm: float | None = None
    right_inlier_span_mm: float | None = None
    normal_uncertainty_deg: float | None = None

    def to_dict(self) -> dict[str, object]:
        """Return stable primitive values suitable for diagnostics JSON."""

        return {
            "reference_point_count": self.reference_point_count,
            "left_reference_count": self.left_reference_count,
            "right_reference_count": self.right_reference_count,
            "iterations_attempted": self.iterations_attempted,
            "valid_model_count": self.valid_model_count,
            "inlier_count": self.inlier_count,
            "left_inlier_count": self.left_inlier_count,
            "right_inlier_count": self.right_inlier_count,
            "rms_mm": self.rms_mm,
            "median_residual_mm": self.median_residual_mm,
            "support_ratio": self.support_ratio,
            "covariance_eigenvalues_mm2": (
                list(self.covariance_eigenvalues_mm2)
                if self.covariance_eigenvalues_mm2 is not None
                else None
            ),
            "left_inlier_span_mm": self.left_inlier_span_mm,
            "right_inlier_span_mm": self.right_inlier_span_mm,
            "normal_uncertainty_deg": self.normal_uncertainty_deg,
        }


class PlaneFitError(RuntimeError):
    """A rejected plane fit that still carries its quantitative evidence."""

    def __init__(
        self, message: str, *, reason_code: str, evidence: PlaneFitEvidence
    ) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.evidence = evidence


def _principal_span_mm(points: FloatArray) -> float:
    if len(points) < 2:
        return 0.0
    centered = points - points.mean(axis=0)
    try:
        _, _, vh = np.linalg.svd(centered, full_matrices=False)
    except np.linalg.LinAlgError:
        return float(np.linalg.norm(np.ptp(points, axis=0)))
    coordinates = centered @ vh[0]
    return float(np.ptp(coordinates))


def _plane_fit_evidence(
    points: FloatArray,
    labels: NDArray[np.int8],
    mask: NDArray[np.bool_] | None,
    *,
    iterations_attempted: int,
    valid_model_count: int,
) -> tuple[PlaneFitEvidence, FloatArray | None]:
    """Measure the best available model without deciding whether to accept it."""

    base = {
        "reference_point_count": int(len(points)),
        "left_reference_count": int(np.sum(labels == 0)),
        "right_reference_count": int(np.sum(labels == 1)),
        "iterations_attempted": int(iterations_attempted),
        "valid_model_count": int(valid_model_count),
    }
    if mask is None or int(mask.sum()) < 3:
        return PlaneFitEvidence(**base), None

    support = points[mask]
    try:
        plane, rms = fit_plane_svd(support)
    except (ValueError, np.linalg.LinAlgError):
        return (
            PlaneFitEvidence(
                **base,
                inlier_count=int(mask.sum()),
                left_inlier_count=int(np.sum(mask & (labels == 0))),
                right_inlier_count=int(np.sum(mask & (labels == 1))),
            ),
            None,
        )
    residuals = np.abs(support @ plane[:3] + plane[3])
    centered = support - support.mean(axis=0)
    covariance = centered.T @ centered / max(1, len(support))
    eigenvalues = np.sort(np.maximum(np.linalg.eigvalsh(covariance), 0.0))
    support_ratio = float(eigenvalues[1] / max(eigenvalues[2], EPSILON))
    normal_uncertainty = float(
        np.degrees(np.arctan2(rms, np.sqrt(max(eigenvalues[1], EPSILON))))
    )
    left_support = points[mask & (labels == 0)]
    right_support = points[mask & (labels == 1)]
    return (
        PlaneFitEvidence(
            **base,
            inlier_count=int(mask.sum()),
            left_inlier_count=int(len(left_support)),
            right_inlier_count=int(len(right_support)),
            rms_mm=float(rms),
            median_residual_mm=float(np.median(residuals)),
            support_ratio=support_ratio,
            covariance_eigenvalues_mm2=tuple(float(value) for value in eigenvalues),
            left_inlier_span_mm=_principal_span_mm(left_support),
            right_inlier_span_mm=_principal_span_mm(right_support),
            normal_uncertainty_deg=normal_uncertainty,
        ),
        plane,
    )


def fit_laser_plane_ransac(
    points: NDArray[np.floating],
    labels: NDArray[np.integer],
    distance_threshold_mm: float = 1.5,
    iterations: int = 160,
    seed: int = 4382,
) -> PlaneFit:
    """Robustly fit a plane while requiring support from both reference walls."""
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    groups = np.asarray(labels, dtype=np.int8).reshape(-1)
    if len(pts) != len(groups) or len(pts) < 6:
        raise ValueError("Laser plane requires at least six labelled reference points")
    left = np.flatnonzero(groups == 0)
    right = np.flatnonzero(groups == 1)
    if len(left) < 2 or len(right) < 2:
        raise ValueError("Laser plane requires samples from both reference walls")
    rng = np.random.default_rng(seed)
    best_mask: NDArray[np.bool_] | None = None
    best_attempt_mask: NDArray[np.bool_] | None = None
    best_score = (-1, -np.inf)
    best_attempt_score = (-1, -np.inf)
    valid_model_count = 0
    for _ in range(iterations):
        if rng.random() < 0.5:
            sample = np.r_[rng.choice(left, 2, replace=False), rng.choice(right, 1)]
        else:
            sample = np.r_[rng.choice(left, 1), rng.choice(right, 2, replace=False)]
        try:
            plane, _ = fit_plane_svd(pts[sample])
        except np.linalg.LinAlgError:
            continue
        valid_model_count += 1
        distances = np.abs(pts @ plane[:3] + plane[3])
        mask = distances <= distance_threshold_mm
        attempt_count = int(mask.sum())
        attempt_median = (
            float(np.median(distances[mask])) if attempt_count else float("inf")
        )
        attempt_score = (attempt_count, -attempt_median)
        if attempt_score > best_attempt_score:
            best_attempt_score = attempt_score
            best_attempt_mask = mask
        left_count = int(np.sum(mask & (groups == 0)))
        right_count = int(np.sum(mask & (groups == 1)))
        if min(left_count, right_count) < 2:
            continue
        count = int(mask.sum())
        median = float(np.median(distances[mask]))
        score = (count, -median)
        if score > best_score:
            best_score = score
            best_mask = mask
    if best_mask is None or int(best_mask.sum()) < 6:
        evidence, _ = _plane_fit_evidence(
            pts,
            groups,
            best_attempt_mask,
            iterations_attempted=iterations,
            valid_model_count=valid_model_count,
        )
        raise PlaneFitError(
            "No stable laser plane could be fitted",
            reason_code="laser_plane_no_stable_model",
            evidence=evidence,
        )
    evidence, plane = _plane_fit_evidence(
        pts,
        groups,
        best_mask,
        iterations_attempted=iterations,
        valid_model_count=valid_model_count,
    )
    if plane is None or evidence.rms_mm is None or evidence.support_ratio is None:
        raise PlaneFitError(
            "The laser plane could not be refined from its inliers",
            reason_code="laser_plane_refinement_failed",
            evidence=evidence,
        )
    if evidence.support_ratio < MIN_PLANE_SUPPORT_RATIO:
        raise PlaneFitError(
            "Reference support is nearly one line; the current laser plane is ambiguous",
            reason_code="laser_plane_degenerate_support",
            evidence=evidence,
        )
    return PlaneFit(
        plane=plane,
        rms_mm=evidence.rms_mm,
        inliers=best_mask,
        support_ratio=evidence.support_ratio,
        normal_uncertainty_deg=float(evidence.normal_uncertainty_deg or 0.0),
        evidence=evidence,
    )


def project_world_points(
    points: NDArray[np.floating],
    camera: CameraCalibration,
    corner: CornerCalibration,
) -> FloatArray:
    source = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    if not len(source):
        return np.empty((0, 2), dtype=np.float64)
    projected, _ = cv2.projectPoints(
        source,
        corner.rvec,
        corner.tvec,
        camera.camera_matrix,
        camera.distortion,
    )
    return projected.reshape(-1, 2)


def polygon_mask(image_shape: tuple[int, int], polygon: NDArray[np.floating]) -> NDArray[np.bool_]:
    mask = np.zeros(image_shape[:2], dtype=np.uint8)
    cv2.fillConvexPoly(mask, np.rint(polygon).astype(np.int32), 255)
    return mask.astype(bool)


def point_in_roi(points: NDArray[np.floating], roi: tuple[int, int, int, int]) -> NDArray[np.bool_]:
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    x, y, width, height = roi
    return (
        (pts[:, 0] >= x)
        & (pts[:, 0] < x + width)
        & (pts[:, 1] >= y)
        & (pts[:, 1] < y + height)
    )
