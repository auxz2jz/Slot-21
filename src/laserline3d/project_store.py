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
    arrays_descriptor: int | None = None
    arrays_temporary: str | None = None
    try:
        arrays_descriptor, arrays_temporary = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".pointcloud.tmp",
            dir=destination.parent,
        )
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
        with os.fdopen(arrays_descriptor, "w+b") as arrays_stream:
            arrays_descriptor = None
            np.savez_compressed(
                arrays_stream,
                points=cloud.points,
                colors=cloud.colors,
                image_points=cloud.image_points,
            )
            arrays_stream.flush()
            os.fsync(arrays_stream.fileno())
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("project.json", json.dumps(manifest, indent=2) + "\n")
            archive.write(
                arrays_temporary,
                "pointcloud.npz",
                compress_type=zipfile.ZIP_STORED,
            )
        os.replace(temporary, destination)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    finally:
        if arrays_descriptor is not None:
            try:
                os.close(arrays_descriptor)
            except OSError:
                pass
        if arrays_temporary is not None:
            try:
                os.unlink(arrays_temporary)
            except OSError:
                pass


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
