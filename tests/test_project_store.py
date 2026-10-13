from pathlib import Path

import numpy as np

from laserline3d.models import PointCloud
from laserline3d.project_store import load_project, save_project
from laserline3d.synthetic import make_synthetic_rig


def test_project_round_trip(tmp_path: Path) -> None:
    rig = make_synthetic_rig()
    cloud = PointCloud(
        points=np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]),
        colors=np.array([[1, 2, 3], [4, 5, 6]], dtype=np.uint8),
        image_points=np.array([[10.0, 11.0], [12.0, 13.0]]),
    )
    path = tmp_path / "sample.llscan"
    save_project(path, cloud, rig.camera, rig.corner, name="sample", metadata={"test": True})
    loaded, camera, corner, manifest = load_project(path)
    assert np.array_equal(loaded.points, cloud.points)
    assert np.array_equal(loaded.colors, cloud.colors)
    assert camera.image_size == rig.camera.image_size
    assert np.allclose(corner.rvec, rig.corner.rvec)
    assert manifest["metadata"]["test"] is True
