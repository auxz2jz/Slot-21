from types import SimpleNamespace

import numpy as np
from PySide6.QtCore import Qt

from laserline3d.telemetry import RunningMetric, ScanEvidenceAccumulator
from laserline3d.ui.main_window import _safe_key_category


def _processed(*, accepted: bool, reason_code: str):
    points = np.array(
        [[1.0, 1.0], [3.0, 2.0], [5.0, 3.0], [7.0, 4.0], [9.0, 5.0]],
        dtype=np.float64,
    )
    classes = np.array([0, 0, 1, 2, -1], dtype=np.int8)
    candidate_mask = np.zeros((8, 12), dtype=bool)
    candidate_mask[1:6, 1:10] = True
    quality = SimpleNamespace(
        accepted=accepted,
        message="sample result",
        reason_code=reason_code,
        detected_points=5,
        object_points=1,
        left_reference_points=2,
        right_reference_points=1,
        support_ratio=0.007,
        plane_rms_mm=0.4,
        median_triangulation_angle_deg=12.0,
        saturated_fraction=0.1,
    )
    detection = SimpleNamespace(
        points=points,
        confidence=np.array([10.0, 20.0, 30.0, 40.0, 50.0]),
        candidate_mask=candidate_mask,
    )
    return SimpleNamespace(quality=quality, detection=detection, point_classes=classes)


def test_running_metric_is_bounded_but_preserves_complete_count_and_extrema() -> None:
    metric = RunningMetric()
    for value in range(3000):
        metric.add(value)
    summary = metric.summary()
    assert summary["count"] == 3000
    assert summary["minimum"] == 0.0
    assert summary["maximum"] == 2999.0
    assert len(metric.recent) == 2048


def test_scan_evidence_separates_roi_outside_and_reference_classes() -> None:
    evidence = ScanEvidenceAccumulator()
    frame = evidence.add(_processed(accepted=False, reason_code="sample_reject"), (4, 2, 4, 4))
    assert frame["classes"]["left_reference"]["count"] == 2
    assert frame["classes"]["object_roi"]["count"] == 1
    assert frame["classes"]["right_reference"]["count"] == 1
    assert frame["classes"]["unclassified"]["count"] == 1
    assert frame["candidate_pixels"]["inside_object_roi"] > 0
    assert frame["candidate_pixels"]["outside_object_roi"] > 0

    summary = evidence.summary()
    assert summary["frames"] == 1
    assert summary["rejected_frames"] == 1
    assert summary["reason_codes"] == {"sample_reject": 1}
    assert summary["class_bounds_px"]["object_roi"] == [5.0, 3.0, 5.0, 3.0]


def test_printable_key_categories_do_not_retain_the_character_identity() -> None:
    assert _safe_key_category(int(Qt.Key.Key_A)) == "printable_or_shortcut_key"
    assert _safe_key_category(int(Qt.Key.Key_Z)) == "printable_or_shortcut_key"
    assert _safe_key_category(int(Qt.Key.Key_0)) == "printable_or_shortcut_key"
    assert _safe_key_category(int(Qt.Key.Key_9)) == "printable_or_shortcut_key"
    assert _safe_key_category(int(Qt.Key.Key_Left)) == "navigate_left"
