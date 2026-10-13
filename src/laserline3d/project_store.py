"""Portable scan-project snapshots (.llscan ZIP containers)."""

from __future__ import annotations

import io
import json
import os
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from .models import CameraCalibration, CornerCalibration, PointCloud


def save_project(
    path: Path,
    cloud: PointCloud,
    camera: CameraCalibration,
    corner: CornerCalibration,
    *,
    name: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    os.close(descriptor)
    manifest = {
        "schema": "laserline3d.project.v1",
        "name": name,
        "saved_utc": datetime.now(timezone.utc).isoformat(),
        "units": "millimetres",
        "point_count": int(len(cloud.points)),
        "camera_calibration": camera.to_dict(),
        "corner_calibration": corner.to_dict(),
        "metadata": metadata or {},
    }
    arrays = io.BytesIO()
    np.savez_compressed(
        arrays,
        points=cloud.points,
        colors=cloud.colors,
        image_points=cloud.image_points,
    )
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("project.json", json.dumps(manifest, indent=2) + "\n")
            archive.writestr("pointcloud.npz", arrays.getvalue())
        os.replace(temporary, destination)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def load_project(
    path: Path,
) -> tuple[PointCloud, CameraCalibration, CornerCalibration, dict[str, Any]]:
    with zipfile.ZipFile(Path(path), "r") as archive:
        manifest = json.loads(archive.read("project.json"))
        with np.load(io.BytesIO(archive.read("pointcloud.npz"))) as arrays:
            cloud = PointCloud(
                points=arrays["points"],
                colors=arrays["colors"],
                image_points=arrays["image_points"],
            )
    return (
        cloud,
        CameraCalibration.from_dict(manifest["camera_calibration"]),
        CornerCalibration.from_dict(manifest["corner_calibration"]),
        manifest,
    )
