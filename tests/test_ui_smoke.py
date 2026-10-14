from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, Signal

from laserline3d.diagnostics import DiagnosticLog
from laserline3d.ui.main_window import MainWindow
from laserline3d.ui.pages import CameraPage, LaserTunePage, RigCalibrationPage, ScanPage
from laserline3d.ui.widgets import PointCloudView
from laserline3d.models import CameraCalibration, PointCloud


class FrameEmitter(QObject):
    frame = Signal(object, float, int)

    def __init__(self, generation: int) -> None:
        super().__init__()
        self.camera_generation = generation

    def isRunning(self) -> bool:
        return False


def test_main_window_constructs_and_closes(qtbot, tmp_path: Path) -> None:
    window = MainWindow(DiagnosticLog(tmp_path / "diagnostics"))
    qtbot.addWidget(window)
    window.show()
    assert window.windowTitle() == "LaserLine 3D Scanner"
    assert window.stack.count() == 7
    assert window.navigation.count() == 7
    generation = window._scan_generation
    window.clear_scan()
    assert window._scan_generation == generation + 1
    assert window.scan_page.scan_state == "ready"
    window.close()


def test_corner_page_explains_order_and_supports_zoom(qtbot) -> None:
    page = RigCalibrationPage()
    qtbot.addWidget(page)
    page.begin_clicking(np.zeros((480, 640, 3), dtype=np.uint8))
    assert "Point 1 of 6" in page.prompt.value.text()
    assert "LEFT outer edge" in page.prompt.value.text()
    assert page.canvas.view_zoom == 1.0
    page.canvas.zoom_in()
    assert page.canvas.view_zoom > 1.0
    page.canvas.reset_view()
    assert page.canvas.view_zoom == 1.0
    page.add_point(20.0, 30.0)
    assert "Point 2 of 6" in page.prompt.value.text()
    page.reset_points()
    assert not page.clicks
    assert not page.capture_object.isEnabled()
    page.await_object_view()
    assert page.capture_object.isEnabled()
    assert page.frozen_frame is None
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    page.begin_roi(frame, (160, 120, 320, 240), [])
    assert page.roi == (160, 120, 320, 240)
    assert page.canvas.interaction_mode == "roi"


def test_scan_page_exposes_unambiguous_button_states(qtbot) -> None:
    page = ScanPage()
    qtbot.addWidget(page)
    assert page.scan_state == "ready"
    assert page.start.text() == "Start scan"
    assert not page.pause.isEnabled()
    assert not page.finish.isEnabled()
    assert not page.clear.isEnabled()

    page.set_scan_state("scanning")
    assert page.start.text() == "Scanning…"
    assert not page.start.isEnabled()
    assert page.pause.isEnabled()
    assert page.finish.isEnabled()

    page.set_scan_state("paused", has_data=True)
    assert page.start.text() == "Resume scan"
    assert page.start.isEnabled()
    assert not page.pause.isEnabled()
    assert page.finish.isEnabled()
    assert page.clear.isEnabled()

    page.set_scan_state("finishing")
    assert page.start.text() == "Finishing…"
    assert not page.finish.isEnabled()
    page.mark_scan_cleared()
    assert page.start.text() == "Start scan"
    assert not page.clear.isEnabled()

    assert page.preview_colors.currentData() == "high_contrast"
    assert page.cloud.color_mode == "high_contrast"
    preview_modes: list[str] = []
    page.preview_mode_changed.connect(preview_modes.append)
    page.preview_colors.setCurrentIndex(1)
    assert page.cloud.color_mode == "surface"
    assert preview_modes == ["surface"]
    assert "exported point colors never change" in page.preview_note.text()

    requested: list[bool] = []
    page.diagnostics_requested.connect(lambda: requested.append(True))
    page.save_diagnostics.click()
    assert requested == [True]
    assert "you choose whether to include" in page.diagnostics_note.text().lower()


def test_point_cloud_high_contrast_preview_preserves_measured_colors(qtbot) -> None:
    view = PointCloudView()
    qtbot.addWidget(view)
    colors = np.array([[0, 0, 0], [30, 5, 2], [220, 180, 40]], dtype=np.uint8)
    cloud = PointCloud(
        points=np.array([[0, 0, 0], [1, 0, 0], [2, 0, 0]], dtype=np.float64),
        colors=colors,
        image_points=np.zeros((3, 2), dtype=np.float64),
    )
    view.set_cloud(cloud)

    display = view._colors_for_display()
    assert display[0].max() >= 190
    assert display[1].max() >= 145
    assert np.array_equal(view._colors, colors)
    assert np.array_equal(cloud.colors, colors)
    view.set_color_mode("surface")
    assert np.array_equal(view._colors_for_display(), colors)


def test_laser_tuning_has_numbers_defaults_and_auto_suggest_action(qtbot) -> None:
    page = LaserTunePage()
    qtbot.addWidget(page)
    requested: list[bool] = []
    restored: list[bool] = []
    page.auto_suggest_requested.connect(lambda: requested.append(True))
    page.defaults_restored.connect(lambda: restored.append(True))

    page.minimum_red.setValue(177)
    assert page.minimum_red_value.text() == "177"
    page.auto_suggest.click()
    assert requested == [True]
    page.restore_defaults()
    assert restored == [True]
    assert (
        page.minimum_red.value(),
        page.dominance.value(),
        page.threshold.value(),
    ) == (120, 45, 55)


def test_camera_page_reports_raw_controls_without_generic_sliders(qtbot) -> None:
    page = CameraPage()
    qtbot.addWidget(page)
    assert not page.settings_button.isEnabled()
    page.set_connected(
        {
            "backend": "DSHOW",
            "width": 1280,
            "height": 720,
            "fps": 30.0,
            "properties": {"Autofocus": 0.0, "Exposure": -6.0, "Zoom": 100.0},
        }
    )
    assert page.settings_button.isEnabled()
    assert "Autofocus: 0" in page.properties.value.text()
    assert "Exposure: -6" in page.properties.value.text()


def test_camera_reconnect_invalidates_changed_geometry_and_background(
    qtbot, tmp_path: Path, monkeypatch
) -> None:
    window = MainWindow(DiagnosticLog(tmp_path / "diagnostics"))
    qtbot.addWidget(window)
    warnings: list[tuple[str, str]] = []
    monkeypatch.setattr(window, "_error", lambda title, message: warnings.append((title, message)))
    window._last_camera_details = {
        "index": 0,
        "backend": "DSHOW",
        "width": 1280,
        "height": 720,
        "properties": {"Autofocus": 0.0, "Focus": 20.0, "Zoom": 100.0},
    }
    window.camera_calibration = CameraCalibration(
        camera_matrix=np.array([[900.0, 0.0, 640.0], [0.0, 900.0, 360.0], [0.0, 0.0, 1.0]]),
        distortion=np.zeros(5),
        image_size=(1280, 720),
        rms_error=0.2,
    )
    window.corner_calibration = object()  # type: ignore[assignment]
    window.background = np.zeros((720, 1280, 3), dtype=np.uint8)
    assert window.disconnect_camera()

    window.on_camera_opened(
        {
            "index": 1,
            "backend": "MSMF",
            "width": 1920,
            "height": 1080,
            "fps": 30.0,
            "properties": {"Autofocus": 1.0, "Focus": 0.0, "Zoom": 100.0},
        }
    )

    assert window.camera_calibration is None
    assert window.corner_calibration is None
    assert window.reconstructor is None
    assert window.background is None
    assert warnings and warnings[0][0] == "Camera geometry changed"
    window.close()


def test_camera_property_change_cancels_partial_background_and_corner_only_calibration(
    qtbot, tmp_path: Path, monkeypatch
) -> None:
    window = MainWindow(DiagnosticLog(tmp_path / "diagnostics"))
    qtbot.addWidget(window)
    monkeypatch.setattr(window, "_error", lambda *_args: None)
    window.camera_details = {
        "properties": {"Focus": 10.0, "Exposure": -5.0},
    }
    window._last_camera_details = dict(window.camera_details)
    window.corner_calibration = object()  # type: ignore[assignment]
    window._background_sum = np.zeros((10, 10, 3), dtype=np.float64)
    window._background_remaining = 9

    window.on_camera_properties_reported({"Focus": 11.0, "Exposure": -6.0})

    assert window._background_sum is None
    assert window._background_remaining == 0
    assert window.corner_calibration is None
    window.close()


def test_stale_camera_frame_and_scan_worker_generation_are_rejected(
    qtbot, tmp_path: Path, monkeypatch
) -> None:
    window = MainWindow(DiagnosticLog(tmp_path / "diagnostics"))
    qtbot.addWidget(window)
    emitter = FrameEmitter(generation=1)
    emitter.frame.connect(window.on_camera_frame)
    window.camera_worker = emitter  # type: ignore[assignment]
    window._camera_generation = 2
    emitter.frame.emit(np.full((4, 4, 3), 255, dtype=np.uint8), 1.0, 7)
    assert window.latest_frame is None

    class OldProcessingWorker:
        def isRunning(self) -> bool:
            return True

    old_generation = window._scan_generation
    observed: list[int] = []
    window.processing_worker = OldProcessingWorker()  # type: ignore[assignment]
    window.camera_worker = object()  # type: ignore[assignment]
    window.latest_frame = np.zeros((4, 4, 3), dtype=np.uint8)
    window.reconstructor = object()  # type: ignore[assignment]
    window.background = np.zeros((4, 4, 3), dtype=np.uint8)
    monkeypatch.setattr(window, "rebuild_reconstructor", lambda: None)
    monkeypatch.setattr(
        window,
        "_discard_processing_worker",
        lambda: observed.append(window._scan_generation),
    )
    monkeypatch.setattr(window, "_confirm_scan_readiness", lambda: True)
    monkeypatch.setattr(window, "_request_camera_snapshot", lambda _context: False)
    monkeypatch.setattr(window, "_error", lambda *_args: None)

    window.start_scan()

    assert observed == [old_generation + 1]
    assert window._scan_generation == old_generation + 1
    window.processing_worker = None
    window.camera_worker = None
    window.close()
