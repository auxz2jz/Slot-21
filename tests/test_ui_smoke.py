import json
import zipfile
from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QFileDialog, QMessageBox

import laserline3d.ui.main_window as main_window_module
from laserline3d.diagnostics import DiagnosticLog
from laserline3d.ui.main_window import MainWindow
from laserline3d.ui.pages import CameraPage, LaserTunePage, RigCalibrationPage, ScanPage
from laserline3d.ui.widgets import PointCloudView
from laserline3d.laser_detection import LaserDetection
from laserline3d.models import CameraCalibration, Mesh, PointCloud, ScanProfile
from laserline3d.reconstruction import FrameQuality, ProcessedFrame
from laserline3d.synthetic import make_synthetic_rig


class FrameEmitter(QObject):
    frame = Signal(object, float, int)

    def __init__(self, generation: int) -> None:
        super().__init__()
        self.camera_generation = generation

    def isRunning(self) -> bool:
        return False


def _review_cloud() -> PointCloud:
    return PointCloud(
        points=np.array([[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [0.0, 2.0, 0.0]]),
        colors=np.full((3, 3), 120, dtype=np.uint8),
        image_points=np.zeros((3, 2), dtype=np.float64),
    )


def _review_mesh(cloud: PointCloud) -> Mesh:
    return Mesh(
        vertices=cloud.points.copy(),
        faces=np.array([[0, 1, 2]], dtype=np.int32),
        colors=cloud.colors.copy(),
    )


def _accepted_processed_frame() -> ProcessedFrame:
    image_points = np.array([[4.0, 5.0]], dtype=np.float64)
    profile = ScanProfile(
        points_world=np.array([[10.0, 20.0, 30.0]], dtype=np.float64),
        colors_rgb=np.array([[80, 90, 100]], dtype=np.uint8),
        image_points=image_points,
        frame_index=1,
        timestamp_s=0.1,
        laser_plane_camera=np.array([0.0, 0.0, 1.0, -100.0]),
        plane_rms_mm=0.2,
        left_reference_count=20,
        right_reference_count=20,
    )
    detection = LaserDetection(
        points=image_points,
        confidence=np.array([0.9], dtype=np.float64),
        score=np.zeros((12, 16), dtype=np.float32),
        candidate_mask=np.zeros((12, 16), dtype=bool),
        orientation="horizontal",
        saturated_fraction=0.0,
    )
    return ProcessedFrame(
        quality=FrameQuality(
            accepted=True,
            message="Good",
            reason_code="accepted",
            detected_points=1,
            object_points=1,
            left_reference_points=20,
            right_reference_points=20,
            plane_rms_mm=0.2,
        ),
        detection=detection,
        profile=profile,
        point_classes=np.array([1], dtype=np.int8),
    )


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


def test_second_finish_preserves_cleaned_cloud_and_mesh(qtbot, tmp_path: Path) -> None:
    diagnostics = DiagnosticLog(tmp_path / "diagnostics")
    window = MainWindow(diagnostics)
    qtbot.addWidget(window)
    cloud = _review_cloud()
    mesh = _review_mesh(cloud)
    window.cleaned_cloud = cloud
    window.mesh = mesh

    window.finish_scan()

    assert window.cleaned_cloud is cloud
    assert window.mesh is mesh
    assert window.review_page.cloud is cloud
    assert window.review_page.mesh is mesh
    assert window.navigation.currentRow() == 6
    assert "scan_finish_reused_reviewed_result" in diagnostics.path.read_text(
        encoding="utf-8"
    )
    window.close()


def test_first_new_accepted_frame_invalidates_review_result(
    qtbot, tmp_path: Path
) -> None:
    diagnostics = DiagnosticLog(tmp_path / "diagnostics")
    window = MainWindow(diagnostics)
    qtbot.addWidget(window)
    cloud = _review_cloud()
    window.cleaned_cloud = cloud
    window.mesh = _review_mesh(cloud)

    processed = _accepted_processed_frame()
    window.on_processed_frame(processed, np.zeros((12, 16, 3), dtype=np.uint8))

    assert window.accumulator.accepted_frames == 1
    assert window.cleaned_cloud is None
    assert window.mesh is None
    assert window.review_page.cloud is None
    log = diagnostics.path.read_text(encoding="utf-8")
    assert log.count('"event":"scan_review_result_invalidated"') == 1

    window.on_processed_frame(processed, np.zeros((12, 16, 3), dtype=np.uint8))
    log = diagnostics.path.read_text(encoding="utf-8")
    assert log.count('"event":"scan_review_result_invalidated"') == 1
    window.close()


def test_complete_test_run_ui_writes_every_canonical_artifact(
    qtbot, tmp_path: Path, monkeypatch
) -> None:
    diagnostics = DiagnosticLog(tmp_path / "diagnostics", app_version="0.4-test")
    window = MainWindow(diagnostics)
    qtbot.addWidget(window)
    rig = make_synthetic_rig(image_size=(160, 120))
    cloud = _review_cloud()
    window.camera_calibration = rig.camera
    window.corner_calibration = rig.corner
    window.cleaned_cloud = cloud
    window.mesh = _review_mesh(cloud)
    window.background = rig.background_bgr
    window.latest_frame = rig.background_bgr.copy()
    window._ensure_raw_fused_spool(cloud)
    window._cloud_cleanup_applied = True
    raw_spool = window._raw_fused_spool_path

    def unexpected_refusion():
        raise AssertionError("complete ZIP must reuse the preserved raw fused cloud")

    monkeypatch.setattr(window.accumulator, "cloud", unexpected_refusion)
    destination = tmp_path / "complete-run.zip"
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *_args, **_kwargs: (str(destination), "ZIP archive (*.zip)"),
    )
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.No,
    )
    monkeypatch.setattr(QMessageBox, "information", lambda *_args, **_kwargs: None)

    run_id = window._test_run_id
    window.save_complete_test_run_bundle()

    assert window._test_run_saved
    assert diagnostics.active_test_run_id is None
    with zipfile.ZipFile(destination) as archive:
        names = set(archive.namelist())
        assert {
            "manifest.json",
            "diagnostics/events.jsonl",
            "run/summary.json",
            "run/settings.json",
            "models/raw/fused-scan.ply",
            "models/raw/fused-scan.ply.json",
            "models/final/scan.ply",
            "models/final/scan.ply.json",
            "models/final/scan.obj",
            "models/final/scan.obj.json",
            "models/final/scan.stl",
            "models/final/scan.stl.json",
            "project/scan.llscan",
            "calibration/camera.json",
            "calibration/corner.json",
        } <= names
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["test_run_id"] == run_id
        assert manifest["package_status"] == "complete"
        assert not any(name.startswith("images/") for name in names)
    window.close()
    assert raw_spool is not None and not raw_spool.exists()


def test_start_new_test_run_clears_scan_but_preserves_reusable_calibration(
    qtbot, tmp_path: Path, monkeypatch
) -> None:
    diagnostics = DiagnosticLog(tmp_path / "diagnostics", app_version="0.4-test")
    window = MainWindow(diagnostics)
    qtbot.addWidget(window)
    rig = make_synthetic_rig(image_size=(160, 120))
    background = rig.background_bgr.copy()
    window.camera_calibration = rig.camera
    window.corner_calibration = rig.corner
    window.background = background
    window.cleaned_cloud = _review_cloud()
    window.mesh = _review_mesh(window.cleaned_cloud)
    window.on_processed_frame(
        _accepted_processed_frame(), np.zeros((12, 16, 3), dtype=np.uint8)
    )
    previous_run_id = window._test_run_id
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )

    window.start_new_test_run()

    assert window._test_run_id is not None
    assert window._test_run_id != previous_run_id
    assert diagnostics.active_test_run_id == window._test_run_id
    assert diagnostics.test_run_metadata(previous_run_id)["status"] == "cancelled"
    assert window.accumulator.accepted_frames == 0
    assert window.accumulator.rejected_frames == 0
    assert window.cleaned_cloud is None
    assert window.mesh is None
    assert window.review_page.cloud is None
    assert window._scan_operation_id is None
    assert window.camera_calibration is rig.camera
    assert window.corner_calibration is rig.corner
    assert window.background is background
    assert window.navigation.currentRow() == 5
    window.close()


def test_main_window_applies_fine_density_to_controller_accumulator_and_snapshot(
    qtbot, tmp_path: Path
) -> None:
    diagnostics = DiagnosticLog(tmp_path / "diagnostics", app_version="0.4-test")
    window = MainWindow(diagnostics)
    qtbot.addWidget(window)

    window.scan_page.set_density_preset("fine")

    assert window.scan_page.selected_density_preset == "fine"
    assert window.current_scan_settings().voxel_size_mm == 0.50
    assert window.current_scan_settings().capture_interval_ms == 80
    assert window.accumulator.voxel_size_mm == 0.50
    assert window.accumulator.max_points == window.current_scan_settings().max_points
    snapshot = window._run_settings_snapshot()
    assert snapshot["scan"]["voxel_size_mm"] == 0.50
    assert snapshot["scan"]["capture_interval_ms"] == 80
    assert '"event":"scan_density_changed"' in diagnostics.path.read_text(
        encoding="utf-8"
    )
    window.close()


def test_complete_test_run_ui_includes_opted_in_images_and_manual_exports(
    qtbot, tmp_path: Path, monkeypatch
) -> None:
    diagnostics = DiagnosticLog(tmp_path / "diagnostics", app_version="0.4-test")
    window = MainWindow(diagnostics)
    qtbot.addWidget(window)
    rig = make_synthetic_rig(image_size=(160, 120))
    cloud = _review_cloud()
    window.camera_calibration = rig.camera
    window.corner_calibration = rig.corner
    window.cleaned_cloud = cloud
    window.mesh = _review_mesh(cloud)
    window.background = rig.background_bgr
    window.latest_frame = rig.background_bgr.copy()
    manual_model = tmp_path / "manual-scan.ply"
    manual_sidecar = tmp_path / "manual-scan.ply.json"
    manual_model.write_bytes(b"older export at the same destination")
    manual_sidecar.write_text('{"source":"older"}\n', encoding="utf-8")
    window._track_run_export(manual_model, manual_sidecar, "point_cloud")
    manual_model.write_bytes(b"manually exported point cloud")
    manual_sidecar.write_text('{"source":"manual"}\n', encoding="utf-8")
    window._track_run_export(manual_model, manual_sidecar, "point_cloud")
    assert len(window._run_exported_artifacts) == 1
    destination = tmp_path / "complete-run-with-images.zip"
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *_args, **_kwargs: (str(destination), "ZIP archive (*.zip)"),
    )
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(QMessageBox, "information", lambda *_args, **_kwargs: None)

    window.save_complete_test_run_bundle()

    assert window._test_run_saved
    with zipfile.ZipFile(destination) as archive:
        names = set(archive.namelist())
        assert "images/current-camera-frame.jpg" in names
        assert "images/laser-off-background.png" in names
        assert "manual-exports/001-manual-scan.ply" in names
        assert "manual-exports/001-manual-scan.ply.json" in names
        assert (
            archive.read("manual-exports/001-manual-scan.ply")
            == b"manually exported point cloud"
        )
        manifest = json.loads(archive.read("manifest.json"))
        items = {item["archive_path"]: item for item in manifest["items"]}
        assert items["images/current-camera-frame.jpg"]["status"] == "included"
        assert items["images/laser-off-background.png"]["status"] == "included"
        assert items["manual-exports/001-manual-scan.ply"]["status"] == "included"
    window.close()


def test_complete_test_run_ui_can_retry_after_atomic_package_failure(
    qtbot, tmp_path: Path, monkeypatch
) -> None:
    diagnostics = DiagnosticLog(tmp_path / "diagnostics", app_version="0.4-test")
    window = MainWindow(diagnostics)
    qtbot.addWidget(window)
    rig = make_synthetic_rig(image_size=(160, 120))
    cloud = _review_cloud()
    window.camera_calibration = rig.camera
    window.corner_calibration = rig.corner
    window.cleaned_cloud = cloud
    window.mesh = _review_mesh(cloud)
    window.background = rig.background_bgr
    destination = tmp_path / "retry-complete-run.zip"
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *_args, **_kwargs: (str(destination), "ZIP archive (*.zip)"),
    )
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.No,
    )
    monkeypatch.setattr(QMessageBox, "information", lambda *_args, **_kwargs: None)
    errors: list[tuple[str, str]] = []
    monkeypatch.setattr(window, "_error", lambda title, message: errors.append((title, message)))
    real_create = main_window_module.create_complete_run_bundle
    attempts = 0

    def fail_once(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError("simulated atomic publish failure")
        return real_create(*args, **kwargs)

    monkeypatch.setattr(main_window_module, "create_complete_run_bundle", fail_once)
    run_id = window._test_run_id

    window.save_complete_test_run_bundle()

    assert attempts == 1
    assert not destination.exists()
    assert not window._test_run_saved
    assert window._test_run_finalized
    assert diagnostics.active_test_run_id is None
    assert window.save_complete_run_button.isEnabled()
    assert errors and "simulated atomic publish failure" in errors[-1][1]

    window.save_complete_test_run_bundle()

    assert attempts == 2
    assert destination.is_file()
    assert window._test_run_saved
    with zipfile.ZipFile(destination) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["test_run_id"] == run_id
        assert manifest["package_status"] == "complete"
        summary = json.loads(archive.read("run/summary.json"))
        requests = summary["package_requests"]
        assert [request["attempt"] for request in requests] == [1, 2]
        assert [request["status"] for request in requests] == ["failed", "requested"]
        assert all(not request["include_private_images"] for request in requests)
    window.close()


def test_complete_test_run_ui_records_partial_status_when_project_is_unavailable(
    qtbot, tmp_path: Path, monkeypatch
) -> None:
    diagnostics = DiagnosticLog(tmp_path / "diagnostics", app_version="0.4-test")
    window = MainWindow(diagnostics)
    qtbot.addWidget(window)
    cloud = _review_cloud()
    window.cleaned_cloud = cloud
    window.mesh = _review_mesh(cloud)
    destination = tmp_path / "partial-run.zip"
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *_args, **_kwargs: (str(destination), "ZIP archive (*.zip)"),
    )
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.No,
    )
    monkeypatch.setattr(QMessageBox, "information", lambda *_args, **_kwargs: None)
    warnings: list[tuple[str, str]] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, title, message, *_args, **_kwargs: warnings.append(
            (title, message)
        ),
    )
    run_id = window._test_run_id

    window.save_complete_test_run_bundle()

    assert not window._test_run_saved
    assert window._test_run_finalized
    assert window.save_complete_run_button.isEnabled()
    assert warnings and warnings[-1][0] == "Partial test package saved"
    assert diagnostics.test_run_metadata(run_id)["status"] == "partial"
    with zipfile.ZipFile(destination) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        items = {item["archive_path"]: item for item in manifest["items"]}
        assert manifest["package_status"] == "partial"
        assert items["calibration/camera.json"]["status"] == "missing"
        assert items["calibration/corner.json"]["status"] == "missing"
        assert items["project/scan.llscan"]["status"] == "missing"
    window.hide()
    window.close()


def test_visible_window_warns_before_closing_with_unsaved_test_evidence(
    qtbot, tmp_path: Path, monkeypatch
) -> None:
    diagnostics = DiagnosticLog(tmp_path / "diagnostics", app_version="0.4-test")
    window = MainWindow(diagnostics)
    qtbot.addWidget(window)
    window.cleaned_cloud = _review_cloud()
    answers = iter(
        [QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes]
    )
    prompt_titles: list[str] = []

    def answer_close(_parent, title, _message, *_args, **_kwargs):
        prompt_titles.append(title)
        return next(answers)

    monkeypatch.setattr(QMessageBox, "question", answer_close)
    window.show()
    qtbot.wait(1)

    first_close = window.close()

    assert first_close is False
    assert window.isVisible()
    assert prompt_titles == ["Close without saving the test?"]
    assert '"event":"application_close_cancelled"' in diagnostics.path.read_text(
        encoding="utf-8"
    )

    second_close = window.close()

    assert second_close is True
    assert not window.isVisible()
    assert prompt_titles == [
        "Close without saving the test?",
        "Close without saving the test?",
    ]
    assert '"event":"application_closed"' in diagnostics.path.read_text(
        encoding="utf-8"
    )


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

    assert page.selected_density_preset == "standard"
    standard = page.selected_scan_settings()
    assert standard.voxel_size_mm == 0.75
    assert standard.capture_interval_ms == 80
    density_modes: list[str] = []
    page.density_preset_changed.connect(density_modes.append)
    page.set_density_preset("fine")
    fine = page.selected_scan_settings()
    assert density_modes == ["fine"]
    assert fine.voxel_size_mm == 0.50
    assert fine.capture_interval_ms == 80
    page.set_scan_state("scanning")
    assert not page.density_preset.isEnabled()
    page.mark_scan_cleared()
    assert page.density_preset.isEnabled()

    assert page.preview_colors.currentData() == "high_contrast"
    assert page.cloud.color_mode == "high_contrast"
    preview_modes: list[str] = []
    page.preview_mode_changed.connect(preview_modes.append)
    page.preview_colors.setCurrentIndex(1)
    assert page.cloud.color_mode == "surface"
    assert preview_modes == ["surface"]
    assert "exported point colors never change" in page.preview_note.text()

    preview_limits: list[int] = []
    page.preview_point_limit_changed.connect(preview_limits.append)
    assert page.preview_points.currentData() == 10_000
    assert page.cloud.point_limit == 10_000
    assert page.preview_count.text() == "Showing 0 of 0 points"
    page.preview_points.setCurrentIndex(1)
    assert preview_limits == [50_000]
    assert page.cloud.point_limit == 50_000

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


def test_point_cloud_preview_limit_reports_sampling_without_changing_cloud(qtbot) -> None:
    view = PointCloudView()
    qtbot.addWidget(view)
    total = 10_021
    points = np.arange(total * 3, dtype=np.float64).reshape(total, 3)
    colors = (np.arange(total * 3).reshape(total, 3) % 256).astype(np.uint8)
    cloud = PointCloud(points=points, colors=colors, image_points=np.zeros((total, 2)))
    original_points = cloud.points.copy()
    original_colors = cloud.colors.copy()
    counts: list[tuple[int, int]] = []
    view.point_counts_changed.connect(lambda displayed, source: counts.append((displayed, source)))

    view.set_cloud(cloud)
    assert counts[-1] == (10_000, total)
    assert view.point_count_text == f"Showing 10,000 of {total:,} points"
    assert view.displayed_point_count == 10_000

    view.set_point_limit(50_000)
    assert counts[-1] == (total, total)
    assert view.displayed_point_count == total
    assert np.array_equal(view._points, original_points)
    assert np.array_equal(view._colors, original_colors)
    assert np.array_equal(cloud.points, original_points)
    assert np.array_equal(cloud.colors, original_colors)


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
