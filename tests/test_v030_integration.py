import json
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from laserline3d.diagnostics import DiagnosticLog
from laserline3d.laser_detection import LaserDetection
from laserline3d.reconstruction import FrameQuality, ProcessedFrame
from laserline3d.ui.main_window import MainWindow


def _read_events(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_observational_camera_change_does_not_invalidate_background(qtbot, tmp_path: Path) -> None:
    diagnostics = DiagnosticLog(tmp_path / "diagnostics")
    window = MainWindow(diagnostics)
    qtbot.addWidget(window)
    window.camera_details = {
        "properties": {"Sensor temperature": 31.0, "Exposure": -6.0}
    }
    window.background = np.zeros((12, 16, 3), dtype=np.uint8)

    window.on_camera_properties_reported(
        {"Sensor temperature": 32.0, "Exposure": -6.0}
    )

    assert window.background is not None
    event = next(
        item for item in reversed(_read_events(diagnostics.path))
        if item["event"] == "camera_properties_reported"
    )
    assert event["details"]["changed"] == {"Sensor temperature": [31.0, 32.0]}
    assert event["details"]["appearance_affecting_changed"] == {}
    window.close()


def test_appearance_camera_change_pauses_scan_and_invalidates_background(
    qtbot, tmp_path: Path
) -> None:
    window = MainWindow(DiagnosticLog(tmp_path / "diagnostics"))
    qtbot.addWidget(window)
    window.camera_details = {"properties": {"Exposure": -6.0}}
    window.background = np.zeros((12, 16, 3), dtype=np.uint8)
    window.scanning = True

    window.on_camera_properties_reported({"Exposure": -7.0})

    assert window.background is None
    assert not window.scanning
    assert "new laser-off background" in window.scan_page.guidance.text()
    window.close()


def test_readiness_requires_stable_recent_frames_and_support_margin(qtbot, tmp_path: Path) -> None:
    window = MainWindow(DiagnosticLog(tmp_path / "diagnostics"))
    qtbot.addWidget(window)
    now = time.monotonic()
    for offset in range(5):
        window._tune_readiness_history.append(
            {
                "time": now - (4 - offset) * 0.1,
                "accepted": True,
                "reason_code": "accepted",
                "message": "Good",
                "left_reference_points": 30,
                "right_reference_points": 30,
                "object_points": 100,
                "support_ratio": 0.007,
                "plane_rms_mm": 0.4,
                "background_drift": 2.0,
                "background_warning": False,
            }
        )
    report = window._scan_readiness_report()
    assert report["ready"] is True
    assert report["consecutive_accepted"] == 5

    window._tune_readiness_history[-1]["support_ratio"] = 0.0035
    report = window._scan_readiness_report()
    assert report["ready"] is False
    assert report["cautions"]
    window.close()


def test_recorded_tune_quality_keeps_machine_reason_code(qtbot, tmp_path: Path) -> None:
    window = MainWindow(DiagnosticLog(tmp_path / "diagnostics"))
    qtbot.addWidget(window)
    result = SimpleNamespace(
        quality=SimpleNamespace(
            accepted=False,
            reason_code="laser_plane_degenerate_support",
            message="ambiguous",
            left_reference_points=25,
            right_reference_points=22,
            object_points=80,
            support_ratio=0.0029,
            plane_rms_mm=0.3,
        )
    )
    window._record_tune_readiness(
        result, background_drift=4.0, background_warning=False
    )
    assert window._tune_readiness_history[-1]["reason_code"] == "laser_plane_degenerate_support"
    window.close()


def test_scan_auto_pauses_after_long_no_line_streak(qtbot, tmp_path: Path) -> None:
    diagnostics = DiagnosticLog(tmp_path / "diagnostics")
    window = MainWindow(diagnostics)
    qtbot.addWidget(window)
    frame = np.zeros((24, 32, 3), dtype=np.uint8)
    detection = LaserDetection(
        points=np.empty((0, 2), dtype=np.float64),
        confidence=np.empty(0, dtype=np.float64),
        score=np.zeros((24, 32), dtype=np.float32),
        candidate_mask=np.zeros((24, 32), dtype=bool),
        orientation="horizontal",
        saturated_fraction=0.0,
    )
    processed = ProcessedFrame(
        quality=FrameQuality(
            accepted=False,
            message="Laser line was not detected",
            reason_code="laser_not_detected",
        ),
        detection=detection,
        profile=None,
        point_classes=np.empty(0, dtype=np.int8),
    )
    window.scanning = True

    for _ in range(50):
        window.on_processed_frame(processed, frame)

    assert not window.scanning
    assert "50 consecutive frames" in window.scan_page.guidance.text()
    assert any(
        item["event"] == "scan_auto_paused_no_line"
        for item in _read_events(diagnostics.path)
    )
    window.close()
