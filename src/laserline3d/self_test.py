"""Fast packaged smoke test that requires neither a display nor a camera."""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np

from .exporters import export_binary_stl, export_point_cloud_ply
from .meshing import build_front_surface
from .models import LaserSettings, ScanSettings
from .reconstruction import FrameReconstructor, ScanAccumulator
from .synthetic import make_synthetic_rig, render_laser_frame


def run_self_test(output_directory: Path | None = None) -> dict[str, object]:
    rig = make_synthetic_rig()
    laser = LaserSettings(
        minimum_red=110,
        minimum_dominance=40,
        threshold=35.0,
        minimum_component_px=5,
        orientation="horizontal",
        use_background=True,
    )
    scan = ScanSettings(
        min_reference_points_per_wall=8,
        ransac_distance_mm=1.8,
        max_plane_rms_mm=2.2,
        voxel_size_mm=1.0,
    )
    reconstructor = FrameReconstructor(rig.camera, rig.corner, laser, scan)
    accumulator = ScanAccumulator(scan.voxel_size_mm)
    quality_messages: list[str] = []
    for index, level in enumerate(np.linspace(45.0, 355.0, 28)):
        frame = render_laser_frame(rig, float(level), seed=index)
        result = reconstructor.process(
            frame,
            frame_index=index,
            timestamp_s=index / 15.0,
            background_bgr=rig.background_bgr,
        )
        quality_messages.append(result.quality.message)
        accumulator.add(result)
    if accumulator.accepted_frames < 20:
        raise AssertionError(
            f"Only {accumulator.accepted_frames}/28 synthetic frames were accepted: "
            f"{quality_messages[-5:]}"
        )
    cloud = accumulator.cloud()
    if len(cloud.points) < 500:
        raise AssertionError(f"Synthetic cloud is unexpectedly sparse: {len(cloud.points)}")
    depth_error = float(np.median(np.abs(cloud.points[:, 2] - rig.object_depth_mm)))
    if depth_error > 2.5:
        raise AssertionError(f"Synthetic median depth error is {depth_error:.3f} mm")
    mesh = build_front_surface(
        cloud, max_image_edge_px=45.0, max_world_edge_mm=24.0
    )
    if len(mesh.faces) < 100:
        raise AssertionError(f"Synthetic mesh is unexpectedly sparse: {len(mesh.faces)}")
    if output_directory is None:
        temporary_context = tempfile.TemporaryDirectory(prefix="laserline3d_selftest_")
        destination = Path(temporary_context.name)
    else:
        temporary_context = None
        destination = Path(output_directory)
        destination.mkdir(parents=True, exist_ok=True)
    ply_path = destination / "self_test_cloud.ply"
    stl_path = destination / "self_test_surface.stl"
    export_point_cloud_ply(ply_path, cloud)
    export_binary_stl(stl_path, mesh)
    expected_stl_size = 84 + 50 * len(mesh.faces)
    if stl_path.stat().st_size != expected_stl_size:
        raise AssertionError("Binary STL length does not match its triangle count")
    result = {
        "status": "passed",
        "accepted_frames": accumulator.accepted_frames,
        "point_count": len(cloud.points),
        "triangle_count": len(mesh.faces),
        "median_depth_error_mm": round(depth_error, 4),
        "output_directory": str(destination) if output_directory else "temporary",
    }
    if temporary_context is not None:
        temporary_context.cleanup()
    return result
