import numpy as np

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
