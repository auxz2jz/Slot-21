from laserline3d.app import _arguments


def test_qt_smoke_arguments() -> None:
    arguments = _arguments(
        ["--qt-smoke-test", "--qt-smoke-output", "report.json"]
    )
    assert arguments.qt_smoke_test is True
    assert arguments.qt_smoke_output.name == "report.json"
