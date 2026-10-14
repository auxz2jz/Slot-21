import numpy as np

import laserline3d.reconstruction as reconstruction
from laserline3d.geometry import PlaneFit, PlaneFitEvidence
from laserline3d.models import LaserSettings, ScanSettings
from laserline3d.reconstruction import FrameReconstructor, ScanAccumulator
from laserline3d.synthetic import make_synthetic_rig, render_laser_frame


def make_reconstructor():
    rig = make_synthetic_rig()
    laser = LaserSettings(
        minimum_red=110,
        minimum_dominance=40,
        threshold=35,
        minimum_component_px=5,
        orientation="horizontal",
    )
    scan = ScanSettings(
        min_reference_points_per_wall=8,
        ransac_distance_mm=1.8,
        max_plane_rms_mm=2.2,
        voxel_size_mm=1.0,
    )
    return rig, FrameReconstructor(rig.camera, rig.corner, laser, scan), scan


def test_synthetic_sweep_recovers_known_depth() -> None:
    rig, reconstructor, scan = make_reconstructor()
    accumulator = ScanAccumulator(scan.voxel_size_mm)
    for index, level in enumerate(np.linspace(50, 300, 20)):
        frame = render_laser_frame(rig, float(level), seed=index)
        result = reconstructor.process(
            frame,
            frame_index=index,
            timestamp_s=index / 15,
            background_bgr=rig.background_bgr,
        )
        accumulator.add(result)
    assert accumulator.accepted_frames >= 15
    cloud = accumulator.cloud()
    assert len(cloud.points) > 400
    error = np.abs(cloud.points[:, 2] - rig.object_depth_mm)
    assert np.median(error) < 2.5
    assert np.percentile(error, 95) < 6.0


def test_missing_right_reference_rejects_current_frame() -> None:
    rig, reconstructor, _ = make_reconstructor()
    frame = render_laser_frame(rig, 170.0)
    x, _y, width, _height = rig.corner.object_roi
    frame[:, x + width :] = rig.background_bgr[:, x + width :]
    result = reconstructor.process(
        frame, frame_index=1, timestamp_s=0.0, background_bgr=rig.background_bgr
    )
    assert not result.quality.accepted
    assert result.profile is None
    assert "right" in result.quality.message.lower()


def test_wrong_camera_resolution_is_blocked() -> None:
    rig, reconstructor, _ = make_reconstructor()
    frame = render_laser_frame(rig, 170.0)[:-1]
    try:
        reconstructor.process(frame, frame_index=0, timestamp_s=0.0)
    except ValueError as error:
        assert "calibration" in str(error).lower()
    else:
        raise AssertionError("Expected resolution mismatch to fail")


def _install_forced_object_geometry(
    monkeypatch, plane: np.ndarray, ray: np.ndarray
) -> None:
    original_rays = reconstruction.image_points_to_rays
    ray_calls = 0

    def controlled_rays(points, camera):
        nonlocal ray_calls
        ray_calls += 1
        if ray_calls <= 2:
            return original_rays(points, camera)
        return np.tile(ray / np.linalg.norm(ray), (len(points), 1))

    def controlled_fit(points, labels, **_kwargs):
        inliers = np.ones(len(points), dtype=bool)
        evidence = PlaneFitEvidence(
            reference_point_count=len(points),
            left_reference_count=int(np.sum(labels == 0)),
            right_reference_count=int(np.sum(labels == 1)),
            iterations_attempted=1,
            valid_model_count=1,
            inlier_count=len(points),
            left_inlier_count=int(np.sum(labels == 0)),
            right_inlier_count=int(np.sum(labels == 1)),
            rms_mm=0.1,
            median_residual_mm=0.05,
            support_ratio=0.1,
            covariance_eigenvalues_mm2=(0.01, 1.0, 10.0),
            left_inlier_span_mm=100.0,
            right_inlier_span_mm=100.0,
            normal_uncertainty_deg=0.1,
        )
        return PlaneFit(
            plane=np.asarray(plane, dtype=np.float64),
            rms_mm=0.1,
            inliers=inliers,
            support_ratio=0.1,
            normal_uncertainty_deg=0.1,
            evidence=evidence,
        )

    monkeypatch.setattr(reconstruction, "image_points_to_rays", controlled_rays)
    monkeypatch.setattr(reconstruction, "fit_laser_plane_ransac", controlled_fit)


def test_low_triangulation_angle_has_distinct_reason_code(monkeypatch) -> None:
    rig, reconstructor, _ = make_reconstructor()
    _install_forced_object_geometry(
        monkeypatch,
        np.array([1.0, 0.0, 0.0, -100.0]),
        np.array([0.04, 0.0, 0.9992]),
    )
    result = reconstructor.process(
        render_laser_frame(rig, 170.0),
        frame_index=2,
        timestamp_s=0.0,
        background_bgr=rig.background_bgr,
    )
    assert not result.quality.accepted
    assert result.quality.reason_code == "triangulation_angle_too_low"
    assert result.quality.low_angle_rejected_points > 0
    assert result.quality.depth_rejected_points == 0
    assert "shallow" in result.quality.message.lower()


def test_outside_depth_has_distinct_reason_code(monkeypatch) -> None:
    rig, reconstructor, _ = make_reconstructor()
    _install_forced_object_geometry(
        monkeypatch,
        np.array([1.0, 0.0, 0.0, -2000.0]),
        np.array([0.5, 0.0, 0.8660254]),
    )
    result = reconstructor.process(
        render_laser_frame(rig, 170.0),
        frame_index=3,
        timestamp_s=0.0,
        background_bgr=rig.background_bgr,
    )
    assert not result.quality.accepted
    assert result.quality.reason_code == "outside_scan_depth_range"
    assert result.quality.low_angle_rejected_points == 0
    assert result.quality.depth_rejected_points > 0
    assert "depth" in result.quality.message.lower()
