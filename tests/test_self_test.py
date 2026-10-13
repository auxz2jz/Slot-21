from pathlib import Path

from laserline3d.self_test import run_self_test


def test_packaged_self_test_pipeline(tmp_path: Path) -> None:
    report = run_self_test(tmp_path)
    assert report["status"] == "passed"
    assert report["accepted_frames"] >= 20
    assert (tmp_path / "self_test_cloud.ply").exists()
    assert (tmp_path / "self_test_surface.stl").exists()
