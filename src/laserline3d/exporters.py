"""Atomic PLY, OBJ, and binary STL exporters using millimetres and Z-up."""

from __future__ import annotations

import json
import os
import struct
import tempfile
from pathlib import Path
from typing import BinaryIO, Callable

import numpy as np

from .models import Mesh, PointCloud


def to_export_coordinates(points: np.ndarray) -> np.ndarray:
    """Convert internal (X right, Y up, Z toward camera) to right-handed Z-up.

    Export axes are X right, Y away from camera, Z up. Units remain millimetres.
    """
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    return np.column_stack((pts[:, 0], -pts[:, 2], pts[:, 1]))


def _atomic_binary(path: Path, writer: Callable[[BinaryIO], None]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            writer(stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _atomic_text(path: Path, writer: Callable[[object], None]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            writer(stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def export_point_cloud_ply(path: Path, cloud: PointCloud) -> None:
    if not len(cloud.points):
        raise ValueError("Cannot export an empty point cloud")
    points = to_export_coordinates(cloud.points).astype("<f4")
    colors = cloud.colors.astype(np.uint8)
    vertex = np.empty(
        len(points),
        dtype=[("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("red", "u1"), ("green", "u1"), ("blue", "u1")],
    )
    vertex["x"], vertex["y"], vertex["z"] = points.T
    vertex["red"], vertex["green"], vertex["blue"] = colors.T
    header = (
        "ply\nformat binary_little_endian 1.0\n"
        "comment LaserLine3D units millimetres; X right, Y away, Z up\n"
        f"element vertex {len(points)}\n"
        "property float x\nproperty float y\nproperty float z\n"
        "property uchar red\nproperty uchar green\nproperty uchar blue\n"
        "end_header\n"
    ).encode("ascii")

    def writer(stream: BinaryIO) -> None:
        stream.write(header)
        stream.write(vertex.tobytes())

    _atomic_binary(Path(path), writer)


def export_mesh_ply(path: Path, mesh: Mesh) -> None:
    if not len(mesh.faces):
        raise ValueError("Cannot export an empty mesh")
    points = to_export_coordinates(mesh.vertices).astype("<f4")
    colors = mesh.colors.astype(np.uint8)
    vertex = np.empty(
        len(points),
        dtype=[("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("red", "u1"), ("green", "u1"), ("blue", "u1")],
    )
    vertex["x"], vertex["y"], vertex["z"] = points.T
    vertex["red"], vertex["green"], vertex["blue"] = colors.T
    faces = np.asarray(mesh.faces, dtype="<i4")
    header = (
        "ply\nformat binary_little_endian 1.0\n"
        "comment LaserLine3D units millimetres; X right, Y away, Z up\n"
        f"element vertex {len(points)}\n"
        "property float x\nproperty float y\nproperty float z\n"
        "property uchar red\nproperty uchar green\nproperty uchar blue\n"
        f"element face {len(faces)}\nproperty list uchar int vertex_indices\n"
        "end_header\n"
    ).encode("ascii")

    def writer(stream: BinaryIO) -> None:
        stream.write(header)
        stream.write(vertex.tobytes())
        for face in faces:
            stream.write(struct.pack("<Biii", 3, *[int(value) for value in face]))

    _atomic_binary(Path(path), writer)


def export_obj(path: Path, mesh: Mesh) -> None:
    if not len(mesh.faces):
        raise ValueError("Cannot export an empty mesh")
    points = to_export_coordinates(mesh.vertices)

    def writer(stream: object) -> None:
        stream.write("# LaserLine3D surface; coordinates are millimetres, Z-up\n")
        for point, color in zip(points, mesh.colors, strict=True):
            r, g, b = color.astype(np.float64) / 255.0
            stream.write(
                f"v {point[0]:.7g} {point[1]:.7g} {point[2]:.7g} {r:.5f} {g:.5f} {b:.5f}\n"
            )
        for face in mesh.faces:
            stream.write(f"f {face[0] + 1} {face[1] + 1} {face[2] + 1}\n")

    _atomic_text(Path(path), writer)


def export_binary_stl(path: Path, mesh: Mesh) -> None:
    if not len(mesh.faces):
        raise ValueError("Cannot export an empty mesh")
    points = to_export_coordinates(mesh.vertices).astype(np.float32)
    triangles = points[mesh.faces]

    def writer(stream: BinaryIO) -> None:
        title = b"LaserLine3D binary STL; coordinates in millimetres"
        stream.write(title.ljust(80, b"\0")[:80])
        stream.write(struct.pack("<I", len(triangles)))
        for triangle in triangles:
            normal = np.cross(triangle[1] - triangle[0], triangle[2] - triangle[0])
            length = float(np.linalg.norm(normal))
            if length > 1e-12:
                normal = normal / length
            else:
                normal = np.zeros(3, dtype=np.float32)
            stream.write(struct.pack("<12fH", *(normal.tolist() + triangle.ravel().tolist()), 0))

    _atomic_binary(Path(path), writer)


def write_export_metadata(path: Path, metadata: dict[str, object]) -> None:
    destination = Path(path)
    payload = {
        "schema": "laserline3d.export.v1",
        "units": "millimetres",
        "coordinate_system": {
            "handedness": "right",
            "x": "right",
            "y": "away from camera",
            "z": "up",
        },
        **metadata,
    }

    def writer(stream: object) -> None:
        json.dump(payload, stream, indent=2)
        stream.write("\n")

    _atomic_text(destination, writer)
