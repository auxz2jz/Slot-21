import tomllib
from pathlib import Path

from laserline3d import __version__
from laserline3d.app import _arguments


def test_qt_smoke_arguments() -> None:
    arguments = _arguments(
        ["--qt-smoke-test", "--qt-smoke-output", "report.json"]
    )
    assert arguments.qt_smoke_test is True
    assert arguments.qt_smoke_output.name == "report.json"


def test_package_and_project_versions_match() -> None:
    project = Path(__file__).resolve().parents[1]
    metadata = tomllib.loads((project / "pyproject.toml").read_text(encoding="utf-8"))
    assert metadata["project"]["version"] == __version__
