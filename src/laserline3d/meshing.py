"""Conservative open-surface construction from the camera-visible point cloud."""

from __future__ import annotations

import numpy as np
from scipy.spatial import Delaunay

from .models import Mesh, PointCloud


def build_front_surface(
    cloud: PointCloud,
    *,
    max_image_edge_px: float = 35.0,
    max_world_edge_mm: float = 20.0,
    minimum_triangle_area_mm2: float = 0.01,
    max_vertices: int = 180_000,
) -> Mesh:
    """Triangulate in camera-image space and reject bridges across scan gaps.

    This deliberately creates only the observed front surface. It does not fill
    unseen backs or claim to produce a watertight solid.
    """
    if len(cloud.points) < 3:
        raise ValueError("At least three scan points are required to build a mesh")
    finite = np.all(np.isfinite(cloud.points), axis=1) & np.all(
        np.isfinite(cloud.image_points), axis=1
    )
    points = cloud.points[finite]
    colors = cloud.colors[finite]
    image = cloud.image_points[finite]
    if len(points) > max_vertices:
        step = int(np.ceil(len(points) / max_vertices))
        points, colors, image = points[::step], colors[::step], image[::step]
    # Qhull rejects exact duplicate image locations. Retain the first sample in
    # each quarter-pixel cell; prior voxel reduction already averages depth.
    quantized = np.rint(image * 4.0).astype(np.int64)
    _, unique_index = np.unique(quantized, axis=0, return_index=True)
    unique_index.sort()
    points, colors, image = (
        points[unique_index],
        colors[unique_index],
        image[unique_index],
    )
    if len(points) < 3:
        raise ValueError("Scan points do not cover a surface")
    try:
        triangles = Delaunay(image, qhull_options="Qbb Qc Qz Q12").simplices
    except Exception as error:
        raise RuntimeError(f"Surface triangulation failed: {error}") from error
    image_triangles = image[triangles]
    world_triangles = points[triangles]
    image_edges = np.stack(
        [
            image_triangles[:, 1] - image_triangles[:, 0],
            image_triangles[:, 2] - image_triangles[:, 1],
            image_triangles[:, 0] - image_triangles[:, 2],
        ],
        axis=1,
    )
    world_edges = np.stack(
        [
            world_triangles[:, 1] - world_triangles[:, 0],
            world_triangles[:, 2] - world_triangles[:, 1],
            world_triangles[:, 0] - world_triangles[:, 2],
        ],
        axis=1,
    )
    image_lengths = np.linalg.norm(image_edges, axis=2)
    world_lengths = np.linalg.norm(world_edges, axis=2)
    cross = np.cross(
        world_triangles[:, 1] - world_triangles[:, 0],
        world_triangles[:, 2] - world_triangles[:, 0],
    )
    areas = 0.5 * np.linalg.norm(cross, axis=1)
    keep = (
        (np.max(image_lengths, axis=1) <= max_image_edge_px)
        & (np.max(world_lengths, axis=1) <= max_world_edge_mm)
        & (areas >= minimum_triangle_area_mm2)
    )
    triangles = triangles[keep].astype(np.int32)
    if not len(triangles):
        raise RuntimeError(
            "No safe surface triangles remained; scan more densely or increase the gap limits"
        )
    # Camera pixels have Y downward, so flip winding into a conventional order.
    triangles[:, [1, 2]] = triangles[:, [2, 1]]
    return Mesh(vertices=points, faces=triangles, colors=colors)


def mesh_bounds(mesh: Mesh) -> tuple[np.ndarray, np.ndarray]:
    if not len(mesh.vertices):
        raise ValueError("Mesh is empty")
    return mesh.vertices.min(axis=0), mesh.vertices.max(axis=0)


def is_watertight(mesh: Mesh) -> bool:
    if not len(mesh.faces):
        return False
    edges = np.sort(
        np.concatenate(
            [
                mesh.faces[:, [0, 1]],
                mesh.faces[:, [1, 2]],
                mesh.faces[:, [2, 0]],
            ]
        ),
        axis=1,
    )
    _, counts = np.unique(edges, axis=0, return_counts=True)
    return bool(np.all(counts == 2))
