"""Per-frame laser triangulation and point-cloud accumulation."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from .geometry import (
    PlaneFitEvidence,
    PlaneFitError,
    corner_wall_planes_world,
    fit_laser_plane_ransac,
    image_points_to_rays,
    intersect_rays_with_plane,
    point_in_roi,
    project_world_points,
    transform_camera_to_world,
    transform_world_to_camera,
    wall_polygons_world,
    world_plane_to_camera,
)
from .laser_detection import LaserDetection, detect_laser
from .models import (
    CameraCalibration,
    CornerCalibration,
    LaserSettings,
    PointCloud,
    ScanProfile,
    ScanSettings,
)


@dataclass(slots=True)
class FrameQuality:
    accepted: bool
    message: str
    reason_code: str = "unprocessed"
    detected_points: int = 0
    unclassified_points: int = 0
    object_points: int = 0
    left_reference_points: int = 0
    right_reference_points: int = 0
    valid_left_reference_points: int = 0
    valid_right_reference_points: int = 0
    plane_rms_mm: float | None = None
    support_ratio: float | None = None
    plane_inlier_count: int = 0
    plane_left_inlier_count: int = 0
    plane_right_inlier_count: int = 0
    plane_median_residual_mm: float | None = None
    plane_covariance_eigenvalues_mm2: tuple[float, float, float] | None = None
    plane_left_span_mm: float | None = None
    plane_right_span_mm: float | None = None
    plane_normal_uncertainty_deg: float | None = None
    triangulation_candidate_points: int = 0
    ray_intersection_valid_points: int = 0
    low_angle_rejected_points: int = 0
    depth_rejected_points: int = 0
    volume_rejected_points: int = 0
    median_triangulation_angle_deg: float | None = None
    saturated_fraction: float = 0.0


@dataclass(slots=True)
class ProcessedFrame:
    quality: FrameQuality
    detection: LaserDetection
    profile: ScanProfile | None
    point_classes: NDArray[np.int8]


def _inside_convex_polygon(
    points: NDArray[np.floating], polygon: NDArray[np.floating]
) -> NDArray[np.bool_]:
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    poly = np.asarray(polygon, dtype=np.float64).reshape(-1, 2)
    cross_signs = []
    for start, end in zip(poly, np.roll(poly, -1, axis=0), strict=True):
        edge = end - start
        relative = pts - start
        cross_signs.append(edge[0] * relative[:, 1] - edge[1] * relative[:, 0])
    crosses = np.asarray(cross_signs)
    return np.all(crosses >= -1e-6, axis=0) | np.all(crosses <= 1e-6, axis=0)


def _sample_rgb(
    image_bgr: NDArray[np.uint8], points: NDArray[np.floating]
) -> NDArray[np.uint8]:
    height, width = image_bgr.shape[:2]
    pixels = np.rint(points).astype(np.int32)
    pixels[:, 0] = np.clip(pixels[:, 0], 0, width - 1)
    pixels[:, 1] = np.clip(pixels[:, 1], 0, height - 1)
    return image_bgr[pixels[:, 1], pixels[:, 0], ::-1].copy()


def _apply_plane_evidence(
    quality: FrameQuality, evidence: PlaneFitEvidence
) -> None:
    """Copy fit-attempt evidence into the per-frame diagnostic record."""

    quality.plane_rms_mm = evidence.rms_mm
    quality.support_ratio = evidence.support_ratio
    quality.plane_inlier_count = evidence.inlier_count
    quality.plane_left_inlier_count = evidence.left_inlier_count
    quality.plane_right_inlier_count = evidence.right_inlier_count
    quality.plane_median_residual_mm = evidence.median_residual_mm
    quality.plane_covariance_eigenvalues_mm2 = (
        evidence.covariance_eigenvalues_mm2
    )
    quality.plane_left_span_mm = evidence.left_inlier_span_mm
    quality.plane_right_span_mm = evidence.right_inlier_span_mm
    quality.plane_normal_uncertainty_deg = evidence.normal_uncertainty_deg


class FrameReconstructor:
    def __init__(
        self,
        camera: CameraCalibration,
        corner: CornerCalibration,
        laser_settings: LaserSettings | None = None,
        scan_settings: ScanSettings | None = None,
    ) -> None:
        self.camera = camera
        self.corner = corner
        self.laser_settings = laser_settings or LaserSettings()
        self.scan_settings = scan_settings or ScanSettings()
        left_world, right_world = wall_polygons_world(corner)
        self.left_polygon = project_world_points(left_world, camera, corner)
        self.right_polygon = project_world_points(right_world, camera, corner)
        left_plane_world, right_plane_world = corner_wall_planes_world(
            corner.hinge_angle_deg
        )
        self.left_plane_camera = world_plane_to_camera(left_plane_world, corner)
        self.right_plane_camera = world_plane_to_camera(right_plane_world, corner)

    def process(
        self,
        frame_bgr: NDArray[np.uint8],
        *,
        frame_index: int,
        timestamp_s: float,
        background_bgr: NDArray[np.uint8] | None = None,
    ) -> ProcessedFrame:
        expected_size = self.camera.image_size
        actual_size = (frame_bgr.shape[1], frame_bgr.shape[0])
        if actual_size != expected_size:
            raise ValueError(
                f"Camera frame is {actual_size[0]}x{actual_size[1]}, but calibration "
                f"is for {expected_size[0]}x{expected_size[1]}"
            )
        detection = detect_laser(frame_bgr, self.laser_settings, background_bgr)
        points = detection.points
        classes = np.full(len(points), -1, dtype=np.int8)
        quality = FrameQuality(
            accepted=False,
            message="Laser line was not detected",
            reason_code="laser_not_detected",
            detected_points=len(points),
            unclassified_points=len(points),
            saturated_fraction=detection.saturated_fraction,
        )
        if len(points) < 10:
            if len(points):
                quality.reason_code = "insufficient_laser_points"
            return ProcessedFrame(quality, detection, None, classes)
        object_mask = point_in_roi(points, self.corner.object_roi)
        left_mask = _inside_convex_polygon(points, self.left_polygon) & ~object_mask
        right_mask = _inside_convex_polygon(points, self.right_polygon) & ~object_mask
        classes[left_mask] = 0
        classes[object_mask] = 1
        classes[right_mask] = 2
        quality.left_reference_points = int(left_mask.sum())
        quality.right_reference_points = int(right_mask.sum())
        quality.object_points = int(object_mask.sum())
        quality.unclassified_points = int(np.sum(classes < 0))
        minimum = self.scan_settings.min_reference_points_per_wall
        if left_mask.sum() < minimum:
            quality.message = "Move the line left so it reaches the left reference wall"
            quality.reason_code = "missing_left_reference"
            return ProcessedFrame(quality, detection, None, classes)
        if right_mask.sum() < minimum:
            quality.message = "Move the line right so it reaches the right reference wall"
            quality.reason_code = "missing_right_reference"
            return ProcessedFrame(quality, detection, None, classes)
        if object_mask.sum() < 3:
            quality.message = "No usable laser segment is inside the object area"
            quality.reason_code = "missing_object_segment"
            return ProcessedFrame(quality, detection, None, classes)
        left_rays = image_points_to_rays(points[left_mask], self.camera)
        right_rays = image_points_to_rays(points[right_mask], self.camera)
        left_3d, valid_left = intersect_rays_with_plane(
            left_rays, self.left_plane_camera
        )
        right_3d, valid_right = intersect_rays_with_plane(
            right_rays, self.right_plane_camera
        )
        reference = np.concatenate([left_3d[valid_left], right_3d[valid_right]])
        labels = np.r_[
            np.zeros(int(valid_left.sum()), dtype=np.int8),
            np.ones(int(valid_right.sum()), dtype=np.int8),
        ]
        quality.valid_left_reference_points = int(valid_left.sum())
        quality.valid_right_reference_points = int(valid_right.sum())
        try:
            plane_fit = fit_laser_plane_ransac(
                reference,
                labels,
                distance_threshold_mm=self.scan_settings.ransac_distance_mm,
                seed=4382 + int(frame_index),
            )
        except PlaneFitError as error:
            _apply_plane_evidence(quality, error.evidence)
            quality.reason_code = error.reason_code
            quality.message = f"Reference line is unstable: {error}"
            return ProcessedFrame(quality, detection, None, classes)
        except (ValueError, RuntimeError, np.linalg.LinAlgError) as error:
            quality.reason_code = "invalid_reference_geometry"
            quality.message = f"Reference line is unstable: {error}"
            return ProcessedFrame(quality, detection, None, classes)
        if plane_fit.evidence is not None:
            _apply_plane_evidence(quality, plane_fit.evidence)
        else:
            # Compatibility for custom callers that construct the older
            # five-field PlaneFit value directly.
            quality.plane_rms_mm = plane_fit.rms_mm
            quality.support_ratio = plane_fit.support_ratio
        if plane_fit.rms_mm > self.scan_settings.max_plane_rms_mm:
            quality.reason_code = "laser_plane_rms_too_high"
            quality.message = "Laser line is too wide or blurred on the reference walls"
            return ProcessedFrame(quality, detection, None, classes)
        object_image = points[object_mask]
        object_rays = image_points_to_rays(object_image, self.camera)
        quality.triangulation_candidate_points = int(len(object_rays))
        incidence = np.abs(object_rays @ plane_fit.plane[:3])
        angles_deg = np.degrees(np.arcsin(np.clip(incidence, 0.0, 1.0)))
        object_camera, ray_valid = intersect_rays_with_plane(
            object_rays, plane_fit.plane
        )
        quality.ray_intersection_valid_points = int(ray_valid.sum())
        if np.any(ray_valid):
            quality.median_triangulation_angle_deg = float(
                np.median(angles_deg[ray_valid])
            )
        angle_valid = ray_valid & (angles_deg >= 5.0)
        quality.low_angle_rejected_points = int(np.sum(ray_valid & ~angle_valid))
        if int(angle_valid.sum()) < 3:
            if int(ray_valid.sum()) < 3:
                quality.reason_code = "ray_plane_intersection_failed"
                quality.message = (
                    "Laser plane does not intersect enough object camera rays"
                )
            else:
                quality.reason_code = "triangulation_angle_too_low"
                quality.message = (
                    "Laser angle is too shallow—translate the line up or down while keeping "
                    "long segments on both walls; do not pivot it toward the center seam"
                )
            return ProcessedFrame(quality, detection, None, classes)
        depths = np.linalg.norm(object_camera, axis=1)
        depth_valid = (
            angle_valid
            & (depths >= self.scan_settings.min_depth_mm)
            & (depths <= self.scan_settings.max_depth_mm)
        )
        quality.depth_rejected_points = int(np.sum(angle_valid & ~depth_valid))
        object_camera = object_camera[depth_valid]
        object_image = object_image[depth_valid]
        accepted_angles = angles_deg[depth_valid]
        if len(object_camera) < 3:
            quality.reason_code = "outside_scan_depth_range"
            quality.message = "Triangulated points fell outside the scan depth range"
            return ProcessedFrame(quality, detection, None, classes)
        object_world = transform_camera_to_world(object_camera, self.corner)
        # Keep a generous region in front of the hinge and within the fixture height.
        half_angle = np.deg2rad(self.corner.hinge_angle_deg / 2.0)
        outer_depth = self.corner.wing_width_mm * np.cos(half_angle)
        bounds = (
            (np.abs(object_world[:, 0]) <= self.corner.wing_width_mm * 1.2)
            & (object_world[:, 1] >= -0.1 * self.corner.height_mm)
            & (object_world[:, 1] <= 1.1 * self.corner.height_mm)
            & (object_world[:, 2] >= -0.25 * self.corner.wing_width_mm)
            & (object_world[:, 2] <= outer_depth + self.corner.wing_width_mm)
        )
        quality.volume_rejected_points = int(np.sum(~bounds))
        object_world = object_world[bounds]
        object_image = object_image[bounds]
        accepted_angles = accepted_angles[bounds]
        if len(object_world) < 3:
            quality.reason_code = "outside_reference_volume"
            quality.message = "Reconstructed line is outside the reference volume"
            return ProcessedFrame(quality, detection, None, classes)
        colour_source = background_bgr if background_bgr is not None else frame_bgr
        colors = _sample_rgb(colour_source, object_image)
        profile = ScanProfile(
            points_world=object_world,
            colors_rgb=colors,
            image_points=object_image,
            frame_index=frame_index,
            timestamp_s=timestamp_s,
            laser_plane_camera=plane_fit.plane,
            plane_rms_mm=plane_fit.rms_mm,
            left_reference_count=int(valid_left.sum()),
            right_reference_count=int(valid_right.sum()),
        )
        quality.accepted = True
        quality.reason_code = "accepted"
        quality.message = "Good—keep moving the line slowly"
        quality.object_points = len(object_world)
        quality.median_triangulation_angle_deg = float(np.median(accepted_angles))
        return ProcessedFrame(quality, detection, profile, classes)


class ScanAccumulator:
    def __init__(self, voxel_size_mm: float = 0.75, max_points: int = 2_000_000) -> None:
        self.voxel_size_mm = float(voxel_size_mm)
        self.max_points = int(max_points)
        self.profiles: list[ScanProfile] = []
        self.rejected_frames = 0

    def add(self, result: ProcessedFrame) -> bool:
        if not result.quality.accepted or result.profile is None:
            self.rejected_frames += 1
            return False
        current_count = sum(len(profile.points_world) for profile in self.profiles)
        if current_count + len(result.profile.points_world) > self.max_points:
            raise RuntimeError("Scan reached its configured point limit")
        self.profiles.append(result.profile)
        return True

    def raw_cloud(self) -> PointCloud:
        return PointCloud.from_profiles(self.profiles)

    def cloud(self) -> PointCloud:
        return voxel_downsample(self.raw_cloud(), self.voxel_size_mm)

    @property
    def accepted_frames(self) -> int:
        return len(self.profiles)


def voxel_downsample(cloud: PointCloud, voxel_size_mm: float) -> PointCloud:
    if not len(cloud.points) or voxel_size_mm <= 0:
        return cloud
    keys = np.floor(cloud.points / voxel_size_mm).astype(np.int64)
    _, inverse, counts = np.unique(keys, axis=0, return_inverse=True, return_counts=True)
    count = len(counts)
    points = np.zeros((count, 3), dtype=np.float64)
    colors = np.zeros((count, 3), dtype=np.float64)
    image = np.zeros((count, 2), dtype=np.float64)
    for axis in range(3):
        points[:, axis] = np.bincount(inverse, weights=cloud.points[:, axis]) / counts
        colors[:, axis] = np.bincount(inverse, weights=cloud.colors[:, axis]) / counts
    for axis in range(2):
        image[:, axis] = np.bincount(inverse, weights=cloud.image_points[:, axis]) / counts
    return PointCloud(points=points, colors=np.rint(colors).astype(np.uint8), image_points=image)


def remove_statistical_outliers(
    cloud: PointCloud, neighbors: int = 16, standard_ratio: float = 2.5
) -> PointCloud:
    if len(cloud.points) <= neighbors + 1:
        return cloud
    from scipy.spatial import cKDTree

    tree = cKDTree(cloud.points)
    distances, _ = tree.query(cloud.points, k=neighbors + 1, workers=-1)
    mean_distance = distances[:, 1:].mean(axis=1)
    limit = float(mean_distance.mean() + standard_ratio * mean_distance.std())
    keep = mean_distance <= limit
    return PointCloud(
        points=cloud.points[keep],
        colors=cloud.colors[keep],
        image_points=cloud.image_points[keep],
    )
