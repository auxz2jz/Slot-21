import cv2
import numpy as np

from laserline3d.geometry import (
    corner_wall_planes_world,
    fit_corner_pose,
    fit_laser_plane_ransac,
    image_points_to_rays,
    intersect_rays_with_plane,
    transform_world_to_camera,
    world_plane_to_camera,
)
from laserline3d.synthetic import make_synthetic_rig


def test_corner_pose_round_trip() -> None:
    rig = make_synthetic_rig()
    fitted = fit_corner_pose(
        rig.corner.image_points,
        rig.camera,
        rig.corner.wing_width_mm,
        rig.corner.height_mm,
        rig.corner.hinge_angle_deg,
    )
    assert fitted.pose_reprojection_error_px < 1e-5
    assert np.allclose(fitted.tvec, rig.corner.tvec, atol=1e-4)


def test_reference_ray_plane_round_trip() -> None:
    rig = make_synthetic_rig()
    half = np.deg2rad(45.0)
    distance = np.linspace(30.0, 270.0, 25)
    world = np.column_stack(
        (-distance * np.sin(half), np.linspace(40.0, 360.0, 25), distance * np.cos(half))
    )
    pixels, _ = cv2.projectPoints(
        world,
        rig.corner.rvec,
        rig.corner.tvec,
        rig.camera.camera_matrix,
        rig.camera.distortion,
    )
    rays = image_points_to_rays(pixels.reshape(-1, 2), rig.camera)
    left_world, _ = corner_wall_planes_world(90.0)
    plane_camera = world_plane_to_camera(left_world, rig.corner)
    reconstructed, valid = intersect_rays_with_plane(rays, plane_camera)
    expected = transform_world_to_camera(world, rig.corner)
    assert valid.all()
    assert np.max(np.linalg.norm(reconstructed - expected, axis=1)) < 1e-6


def test_robust_laser_plane_with_outliers() -> None:
    rng = np.random.default_rng(12)
    # y = 80 + .12*x + .2*z
    left_x = np.linspace(-220, -20, 70)
    left_z = -left_x
    right_x = np.linspace(20, 220, 70)
    right_z = right_x
    points = np.column_stack(
        (
            np.r_[left_x, right_x],
            80 + 0.12 * np.r_[left_x, right_x] + 0.2 * np.r_[left_z, right_z],
            np.r_[left_z, right_z],
        )
    )
    points += rng.normal(0.0, 0.15, points.shape)
    labels = np.r_[np.zeros(70, dtype=np.int8), np.ones(70, dtype=np.int8)]
    outliers = rng.uniform([-220, 0, 0], [220, 200, 250], size=(25, 3))
    points = np.r_[points, outliers]
    labels = np.r_[labels, rng.integers(0, 2, len(outliers), dtype=np.int8)]
    fit = fit_laser_plane_ransac(points, labels, 0.8, iterations=300)
    expected_normal = np.array([-0.12, 1.0, -0.2])
    expected_normal /= np.linalg.norm(expected_normal)
    angular = np.degrees(np.arccos(np.clip(abs(fit.plane[:3] @ expected_normal), 0, 1)))
    assert angular < 0.2
    assert fit.rms_mm < 0.3
    assert fit.support_ratio > 0.003


def test_parallel_and_behind_rays_are_invalid() -> None:
    rays = np.array([[1.0, 0, 0], [0, 0, 1.0], [0, 0, -1.0]])
    points, valid = intersect_rays_with_plane(rays, np.array([0, 0, 1.0, -10.0]))
    assert valid.tolist() == [False, True, False]
    assert np.allclose(points[1], [0, 0, 10])
