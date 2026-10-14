from __future__ import annotations

import numpy as np
import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

from laserline3d.ui.pages import RigCalibrationPage
from laserline3d.ui.widgets import VideoCanvas


def _ready_canvas(qtbot) -> VideoCanvas:
    canvas = VideoCanvas()
    canvas.resize(800, 600)
    qtbot.addWidget(canvas)
    canvas.show()
    canvas.set_frame(np.zeros((480, 640, 3), dtype=np.uint8))
    QApplication.processEvents()
    return canvas


def test_wheel_zoom_keeps_image_point_under_pointer(qtbot) -> None:
    canvas = _ready_canvas(qtbot)
    anchor = QPointF(650.0, 150.0)
    before = canvas._to_image(anchor)
    assert before is not None
    events: list[dict[str, object]] = []
    canvas.interaction_event.connect(events.append)

    wheel = QWheelEvent(
        anchor,
        QPointF(canvas.mapToGlobal(anchor.toPoint())),
        QPoint(),
        QPoint(0, 120),
        Qt.NoButton,
        Qt.NoModifier,
        Qt.ScrollUpdate,
        False,
    )
    QApplication.sendEvent(canvas, wheel)

    after = canvas._to_image(anchor)
    assert canvas.view_zoom == pytest.approx(1.25)
    assert after == pytest.approx(before)
    assert events[-1]["action"] == "view_zoom"
    assert events[-1]["source"] == "wheel"


def test_short_left_click_places_point_but_left_drag_only_pans(qtbot) -> None:
    canvas = _ready_canvas(qtbot)
    canvas.set_interaction_mode("point")
    points: list[tuple[float, float]] = []
    events: list[dict[str, object]] = []
    canvas.point_clicked.connect(lambda x, y: points.append((x, y)))
    canvas.interaction_event.connect(events.append)

    QTest.mouseClick(canvas, Qt.LeftButton, Qt.NoModifier, QPoint(400, 300))
    assert points == pytest.approx([(320.0, 240.0)])
    assert events[-1]["action"] == "point_placed"

    QTest.mousePress(canvas, Qt.LeftButton, Qt.NoModifier, QPoint(400, 300))
    QTest.mouseMove(canvas, QPoint(455, 335), 1)
    QTest.mouseRelease(canvas, Qt.LeftButton, Qt.NoModifier, QPoint(455, 335))

    assert len(points) == 1
    assert canvas._view_pan.x() == pytest.approx(55.0)
    assert canvas._view_pan.y() == pytest.approx(35.0)
    assert events[-1]["action"] == "view_pan"
    assert events[-1]["button"] == "left"


@pytest.mark.parametrize("button,name", [(Qt.RightButton, "right"), (Qt.MiddleButton, "middle")])
def test_right_and_middle_drag_continue_to_pan(qtbot, button, name: str) -> None:
    canvas = _ready_canvas(qtbot)
    events: list[dict[str, object]] = []
    canvas.interaction_event.connect(events.append)

    QTest.mousePress(canvas, button, Qt.NoModifier, QPoint(300, 250))
    QTest.mouseMove(canvas, QPoint(330, 270), 1)
    QTest.mouseRelease(canvas, button, Qt.NoModifier, QPoint(330, 270))

    assert canvas._view_pan.x() == pytest.approx(30.0)
    assert canvas._view_pan.y() == pytest.approx(20.0)
    assert events[-1]["action"] == "view_pan"
    assert events[-1]["button"] == name


def test_rig_page_forwards_privacy_safe_canvas_interactions(qtbot) -> None:
    page = RigCalibrationPage()
    qtbot.addWidget(page)
    observed: list[dict[str, object]] = []
    page.interaction_event.connect(observed.append)
    page.begin_clicking(np.zeros((480, 640, 3), dtype=np.uint8))

    page.canvas.zoom_in()
    page.canvas.reset_view()

    assert [item["action"] for item in observed[-2:]] == ["view_zoom", "view_reset"]
    assert all("text" not in item for item in observed)
