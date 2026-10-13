"""Deterministic virtual rig used by tests and the no-camera demo."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
from numpy.typing import NDArray

from .geometry import corner_landmarks, project_world_points, rotation_matrix
from .models import CameraCalibration, CornerCalibration


@dataclass(slots=True)
class SyntheticRig:
    camera: CameraCalibration
    corner: CornerCalibration
    background_bgr: NDArray[np.uint8]
    object_depth_mm: float = 255.0


def make_synthetic_rig(
    image_size: tuple[int, int] = (800, 600),
    wing_width_mm: float = 300.0,
    height_mm: float = 400.0,
) -> SyntheticRig:
    width, height = image_size
    focal = 880.0
    matrix = np.asarray(
        [[focal, 0.0, width / 2], [0.0, focal, height / 2], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )
    camera = CameraCalibration(
        camera_matrix=matrix,
        distortion=np.zeros(5),
        image_size=image_size,
        rms_error=0.15,
        accepted_views=18,
        mean_reprojection_error_px=0.12,
    )
    # Camera is at (0, 200, 950) in world space and looks toward world -Z.
    rvec = np.asarray([np.pi, 0.0, 0.0], dtype=np.float64)
    camera_center = np.asarray([0.0, 200.0, 950.0])
    tvec = -(rotation_matrix(rvec) @ camera_center)
    landmarks = corner_landmarks(wing_width_mm, height_mm, 90.0)
    temporary = CornerCalibration(
        rvec=rvec,
        tvec=tvec,
        wing_width_mm=wing_width_mm,
        height_mm=height_mm,
        hinge_angle_deg=90.0,
        image_points=np.zeros((6, 2)),
        object_roi=(1, 1, 2, 2),
    )
    image_points = project_world_points(landmarks, camera, temporary)
    object_corners_world = np.asarray(
        [
            [-85.0, 25.0, 255.0],
            [85.0, 25.0, 255.0],
            [85.0, 375.0, 255.0],
            [-85.0, 375.0, 255.0],
        ]
    )
    object_pixels = project_world_points(object_corners_world, camera, temporary)
    x0, y0 = np.floor(object_pixels.min(axis=0) - 5).astype(int)
    x1, y1 = np.ceil(object_pixels.max(axis=0) + 5).astype(int)
    corner = CornerCalibration(
        rvec=rvec,
        tvec=tvec,
        wing_width_mm=wing_width_mm,
        height_mm=height_mm,
        hinge_angle_deg=90.0,
        image_points=image_points,
        object_roi=(int(x0), int(y0), int(x1 - x0), int(y1 - y0)),
        pose_reprojection_error_px=0.0,
    )
    background = np.full((height, width, 3), 28, dtype=np.uint8)
    # Render reference panels and a neutral object rectangle for natural colours.
    left_polygon = np.rint(image_points[[0, 1, 3, 2]]).astype(np.int32)
    right_polygon = np.rint(image_points[[2, 3, 5, 4]]).astype(np.int32)
    cv2.fillConvexPoly(background, left_polygon, (165, 165, 165))
    cv2.fillConvexPoly(background, right_polygon, (185, 185, 185))
    object_poly = np.rint(object_pixels).astype(np.int32)
    cv2.fillConvexPoly(background, object_poly, (80, 115, 150))
    return SyntheticRig(camera, corner, background)


def _laser_y(x: NDArray[np.float64], z: NDArray[np.float64], level_mm: float) -> NDArray[np.float64]:
    # A handheld sheet angled in depth to create a useful triangulation angle.
    # The world intersection still appears approximately horizontal in-camera.
    return level_mm + 0.035 * x + 0.18 * z


def _render_polyline(
    image: NDArray[np.uint8], pixels: NDArray[np.float64], thickness: int = 3
) -> None:
    valid = np.all(np.isfinite(pixels), axis=1)
    points = np.rint(pixels[valid]).astype(np.int32)
    if len(points) >= 2:
        cv2.polylines(image, [points], False, (25, 35, 245), thickness, cv2.LINE_AA)


def render_laser_frame(
    rig: SyntheticRig,
    level_mm: float,
    *,
    noise_sigma: float = 1.5,
    seed: int = 0,
) -> NDArray[np.uint8]:
    frame = rig.background_bgr.copy()
    half = np.deg2rad(rig.corner.hinge_angle_deg / 2.0)
    # Wall witness lines. Avoid the central object projection only at
    # classification time; physically the line remains visible around it.
    s = np.linspace(0.0, rig.corner.wing_width_mm, 360)
    left_x, left_z = -s * np.sin(half), s * np.cos(half)
    right_x, right_z = s * np.sin(half), s * np.cos(half)
    left_y = _laser_y(left_x, left_z, level_mm)
    right_y = _laser_y(right_x, right_z, level_mm)
    left_world = np.column_stack((left_x, left_y, left_z))
    right_world = np.column_stack((right_x, right_y, right_z))
    left_valid = (left_y >= 0.0) & (left_y <= rig.corner.height_mm)
    right_valid = (right_y >= 0.0) & (right_y <= rig.corner.height_mm)
    left_pixels = project_world_points(left_world[left_valid], rig.camera, rig.corner)
    right_pixels = project_world_points(right_world[right_valid], rig.camera, rig.corner)
    roi_x, _roi_y, roi_w, _roi_h = rig.corner.object_roi
    # The object occludes the wall behind its central image area.
    left_pixels = left_pixels[left_pixels[:, 0] < roi_x]
    right_pixels = right_pixels[right_pixels[:, 0] >= roi_x + roi_w]
    _render_polyline(frame, left_pixels)
    _render_polyline(frame, right_pixels)
    # Front-facing test object: a flat measured surface at known depth.
    object_x = np.linspace(-85.0, 85.0, 260)
    object_z = np.full_like(object_x, rig.object_depth_mm)
    object_y = _laser_y(object_x, object_z, level_mm)
    object_world = np.column_stack((object_x, object_y, object_z))
    valid = (object_y >= 25.0) & (object_y <= 375.0)
    _render_polyline(
        frame,
        project_world_points(object_world[valid], rig.camera, rig.corner),
        thickness=3,
    )
    if noise_sigma > 0:
        rng = np.random.default_rng(seed)
        noise = rng.normal(0.0, noise_sigma, frame.shape).astype(np.float32)
        frame = np.clip(frame.astype(np.float32) + noise, 0, 255).astype(np.uint8)
    return frame
