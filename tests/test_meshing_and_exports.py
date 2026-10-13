import struct
from pathlib import Path

import numpy as np

from laserline3d.exporters import (
    export_binary_stl,
    export_mesh_ply,
    export_obj,
    export_point_cloud_ply,
    to_export_coordinates,
)
from laserline3d.meshing import build_front_surface
from laserline3d.models import Mesh, PointCloud


def grid_cloud() -> PointCloud:
    x, y = np.meshgrid(np.linspace(-20, 20, 16), np.linspace(10, 45, 14))
    z = 100 + 0.02 * x * x + 0.01 * y * y
    points = np.column_stack((x.ravel(), y.ravel(), z.ravel()))
    image = np.column_stack(((x.ravel() + 20) * 4, (y.ravel() - 10) * 4))
    colors = np.tile(np.array([[90, 140, 220]], dtype=np.uint8), (len(points), 1))
    return PointCloud(points, colors, image)


def test_front_surface_has_no_degenerate_faces() -> None:
    mesh = build_front_surface(
        grid_cloud(), max_image_edge_px=20, max_world_edge_mm=10
    )
    assert len(mesh.faces) > 300
    triangles = mesh.vertices[mesh.faces]
    area2 = np.linalg.norm(
        np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]),
        axis=1,
    )
    assert np.all(area2 > 0)


def test_export_coordinate_system_is_right_handed() -> None:
    basis = to_export_coordinates(np.eye(3))
    assert np.allclose(np.cross(basis[0], basis[1]), basis[2])


def test_point_cloud_and_mesh_exports(tmp_path: Path) -> None:
    cloud = grid_cloud()
    mesh = build_front_surface(cloud, max_image_edge_px=20, max_world_edge_mm=10)
    cloud_path = tmp_path / "cloud.ply"
    mesh_path = tmp_path / "mesh.ply"
    obj_path = tmp_path / "mesh.obj"
    stl_path = tmp_path / "mesh.stl"
    export_point_cloud_ply(cloud_path, cloud)
    export_mesh_ply(mesh_path, mesh)
    export_obj(obj_path, mesh)
    export_binary_stl(stl_path, mesh)
    assert cloud_path.read_bytes().startswith(b"ply\nformat binary_little_endian")
    assert mesh_path.read_bytes().startswith(b"ply\nformat binary_little_endian")
    assert obj_path.read_text(encoding="utf-8").count("\nf ") == len(mesh.faces)
    data = stl_path.read_bytes()
    triangle_count = struct.unpack("<I", data[80:84])[0]
    assert triangle_count == len(mesh.faces)
    assert len(data) == 84 + 50 * len(mesh.faces)
