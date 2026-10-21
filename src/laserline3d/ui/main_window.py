from __future__ import annotations

import json
import tempfile
import time
import uuid
from collections import Counter, deque
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from PySide6.QtCore import QEvent, QStandardPaths, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QStackedWidget,
    QToolBar,
    QWidget,
)

from .. import __version__
from ..calibration import (
    ChessboardCalibrator,
    load_camera_calibration,
    load_corner_calibration,
    save_camera_calibration,
    save_corner_calibration,
)
from ..camera import CameraRequest, CameraWorker, describe_camera_properties
from ..diagnostics import DiagnosticLog, frame_statistics
from ..exporters import (
    export_binary_stl,
    export_obj,
    export_point_cloud_ply,
    write_export_metadata,
)
from ..geometry import fit_corner_pose
from ..laser_detection import suggest_laser_settings
from ..meshing import build_front_surface, is_watertight
from ..models import (
    CameraCalibration,
    CornerCalibration,
    LaserSettings,
    Mesh,
    PointCloud,
    ScanSettings,
    settings_dict,
)
from ..processing_worker import FramePacket, ProcessingWorker
from ..project_store import load_project, save_project
from ..reconstruction import (
    FrameReconstructor,
    ScanAccumulator,
    remove_statistical_outliers,
)
from ..resources import CHECKERBOARD_PDF, SETUP_GUIDE_PDF, printable_path
from ..run_bundle import (
    ArtifactRelationship,
    RunBundleArtifact,
    RunBundleCancelledError,
    create_complete_run_bundle,
)
from ..synthetic import make_synthetic_rig, render_laser_frame
from ..telemetry import ScanEvidenceAccumulator
from .pages import (
    CameraPage,
    LaserTunePage,
    LensCalibrationPage,
    ReviewPage,
    RigCalibrationPage,
    ScanPage,
    WelcomePage,
)


class MainWindow(QMainWindow):
    PAGE_NAMES = [
        "Start",
        "1  Camera",
        "2  Calibrate camera lens",
        "3  Build & calibrate corner",
        "4  Tune laser",
        "5  Scan",
        "6  Review & export",
    ]

    def __init__(self, diagnostics: DiagnosticLog) -> None:
        super().__init__()
        self.diagnostics = diagnostics
        self.setWindowTitle("LaserLine 3D Scanner")
        self.resize(1320, 850)
        self.setMinimumSize(1040, 690)

        self.camera_worker: CameraWorker | None = None
        self.processing_worker: ProcessingWorker | None = None
        self.latest_frame: np.ndarray | None = None
        self.latest_timestamp = 0.0
        self.latest_sequence = 0
        self.camera_details: dict[str, object] | None = None
        self._last_camera_details: dict[str, object] | None = None
        self._camera_generation = 0
        self.camera_calibration: CameraCalibration | None = None
        self.corner_calibration: CornerCalibration | None = None
        self.calibrator: ChessboardCalibrator | None = None
        self.background: np.ndarray | None = None
        self._background_captured_monotonic = 0.0
        self._background_sum: np.ndarray | None = None
        self._background_remaining = 0
        self.reconstructor: FrameReconstructor | None = None
        # Keep one immutable-in-practice settings snapshot for the lifetime of
        # a scan.  The UI selector is disabled once capture starts, but this
        # controller snapshot also prevents programmatic UI changes from
        # mixing voxel sizes or capture intervals in one scan.
        self._active_scan_settings = ScanSettings()
        self.accumulator = ScanAccumulator(
            self._active_scan_settings.voxel_size_mm,
            self._active_scan_settings.max_points,
        )
        self.cleaned_cloud: PointCloud | None = None
        self.mesh: Mesh | None = None
        self.scanning = False
        self._last_submit_time = 0.0
        self._finish_pending = False
        self._tune_last_time = 0.0
        self._tune_diagnostic_time = 0.0
        self._tune_diagnostic_status = ""
        self._processed_frame_count = 0
        self._scan_generation = 0
        self._scan_operation_id: str | None = None
        self._scan_rejection_counts: Counter[str] = Counter()
        self._scan_evidence = ScanEvidenceAccumulator()
        self._last_scan_detail_log_time = 0.0
        self._last_scan_reason_code = ""
        self._no_line_streak = 0
        self._test_run_id: str | None = None
        self._test_run_finalized = False
        self._test_run_saved = False
        self._run_exported_artifacts: list[tuple[Path, Path, str]] = []
        self._run_package_requests: list[dict[str, object]] = []
        self._test_run_end_frame: np.ndarray | None = None
        self._test_run_frozen_settings: dict[str, object] | None = None
        self._raw_fused_spool: tempfile.TemporaryDirectory[str] | None = None
        self._raw_fused_spool_path: Path | None = None
        self._raw_fused_point_count = 0
        self._cloud_cleanup_applied = False
        self._latest_tune_result: object | None = None
        self._latest_tune_result_time = 0.0
        self._tune_readiness_history: deque[dict[str, object]] = deque(maxlen=12)
        self._camera_snapshot_pending: str | None = None
        self._last_frame_statistics_time = 0.0
        self._laser_log_timer = QTimer(self)
        self._laser_log_timer.setSingleShot(True)
        self._laser_log_timer.setInterval(300)
        self._laser_log_timer.timeout.connect(self._log_laser_settings)
        self._camera_snapshot_timer = QTimer(self)
        self._camera_snapshot_timer.setInterval(15_000)
        self._camera_snapshot_timer.timeout.connect(self._request_periodic_camera_snapshot)
        self._camera_snapshot_timer.start()

        self.navigation = QListWidget()
        self.navigation.setObjectName("workflowNavigation")
        self.navigation.setFixedWidth(205)
        for name in self.PAGE_NAMES:
            item = QListWidgetItem(name)
            item.setSizeHint(item.sizeHint().expandedTo(item.sizeHint() + _size(0, 18)))
            self.navigation.addItem(item)
        self.stack = QStackedWidget()
        self.welcome_page = WelcomePage()
        self.camera_page = CameraPage()
        self.lens_page = LensCalibrationPage()
        self.rig_page = RigCalibrationPage()
        self.tune_page = LaserTunePage()
        self.scan_page = ScanPage()
        self.review_page = ReviewPage()
        for page in (
            self.welcome_page,
            self.camera_page,
            self.lens_page,
            self.rig_page,
            self.tune_page,
            self.scan_page,
            self.review_page,
        ):
            self.stack.addWidget(page)
        shell = QWidget()
        layout = QHBoxLayout(shell)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.navigation)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(shell)
        self._create_test_run_toolbar()
        self.navigation.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.navigation.currentRowChanged.connect(self._page_changed)
        self.navigation.setCurrentRow(0)
        self._connect_page_actions()
        self._start_test_run(initial=True)
        application = QApplication.instance()
        if application is not None:
            application.installEventFilter(self)
        self.diagnostics.event(
            "interaction_logging_enabled",
            state="privacy_safe",
            result="ok",
            coverage=(
                "In-application key presses, clicks, wheel actions, named controls, and workflow actions"
            ),
            exclusions=(
                "No key text, typed field contents, clipboard data, global activity, camera images, or files"
            ),
        )

    def _connect_page_actions(self) -> None:
        self.welcome_page.connect_camera.connect(lambda: self.navigation.setCurrentRow(1))
        self.welcome_page.synthetic_demo.connect(self.run_synthetic_demo)
        self.welcome_page.open_project.connect(self.open_project_dialog)
        self.camera_page.connect_requested.connect(self.connect_camera)
        self.camera_page.disconnect_requested.connect(self.disconnect_camera)
        self.camera_page.native_settings_requested.connect(self.open_native_camera_settings)
        self.camera_page.refresh_properties_requested.connect(
            self.refresh_camera_properties
        )
        self.lens_page.capture_requested.connect(self.capture_calibration_view)
        self.lens_page.reset_requested.connect(self.reset_calibration_views)
        self.lens_page.calculate_requested.connect(self.calculate_camera_calibration)
        self.lens_page.load_requested.connect(self.load_camera_dialog)
        self.lens_page.open_checkerboard_requested.connect(self.open_checkerboard_pdf)
        self.lens_page.open_guide_requested.connect(self.open_setup_guide_pdf)
        self.rig_page.freeze_requested.connect(self.freeze_rig_image)
        self.rig_page.solve_requested.connect(self.solve_corner)
        self.rig_page.capture_object_view_requested.connect(self.capture_object_view)
        self.rig_page.save_requested.connect(self.save_corner_dialog)
        self.rig_page.load_requested.connect(self.load_corner_dialog)
        self.rig_page.open_guide_requested.connect(self.open_setup_guide_pdf)
        self.rig_page.interaction_event.connect(self._log_corner_interaction)
        self.tune_page.background_requested.connect(self.capture_background)
        self.tune_page.settings_changed.connect(self._laser_settings_changed)
        self.tune_page.auto_suggest_requested.connect(self.auto_suggest_laser_settings)
        self.tune_page.defaults_restored.connect(self._laser_defaults_restored)
        self.scan_page.start_requested.connect(self.start_scan)
        self.scan_page.pause_requested.connect(self.pause_scan)
        self.scan_page.finish_requested.connect(self.finish_scan)
        self.scan_page.clear_requested.connect(self.clear_scan)
        self.scan_page.diagnostics_requested.connect(self.save_diagnostics_bundle)
        self.scan_page.preview_mode_changed.connect(self.on_preview_mode_changed)
        self.scan_page.density_preset_changed.connect(self.on_scan_density_preset_changed)
        self.scan_page.preview_point_limit_changed.connect(
            self.on_preview_point_limit_changed
        )
        self.review_page.clean_requested.connect(self.clean_cloud)
        self.review_page.mesh_requested.connect(self.create_mesh)
        self.review_page.save_project_requested.connect(self.save_project_dialog)
        self.review_page.export_ply_requested.connect(self.export_ply_dialog)
        self.review_page.export_obj_requested.connect(self.export_obj_dialog)
        self.review_page.export_stl_requested.connect(self.export_stl_dialog)

    def _create_test_run_toolbar(self) -> None:
        """Keep physical-test boundaries visible throughout the workflow."""

        toolbar = QToolBar("Physical test run", self)
        toolbar.setObjectName("testRunToolbar")
        toolbar.setMovable(False)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)
        self.test_run_status = QLabel("Preparing test run…")
        self.test_run_status.setObjectName("fieldHelp")
        toolbar.addWidget(self.test_run_status)
        toolbar.addSeparator()
        self.new_test_run_button = QPushButton("Start new test run")
        self.new_test_run_button.setToolTip(
            "Ends the current run and clears its scan data while keeping reusable calibration."
        )
        self.new_test_run_button.clicked.connect(self.start_new_test_run)
        toolbar.addWidget(self.new_test_run_button)
        self.save_complete_run_button = QPushButton("Finish test & save complete ZIP…")
        self.save_complete_run_button.setObjectName("primaryButton")
        self.save_complete_run_button.setToolTip(
            "Last step for a physical test: packages diagnostics, project data, PLY, OBJ, STL, and JSON sidecars."
        )
        self.save_complete_run_button.clicked.connect(
            self.save_complete_test_run_bundle
        )
        toolbar.addWidget(self.save_complete_run_button)

    def _update_test_run_status(self, message: str | None = None) -> None:
        run_short = self._test_run_id[:8] if self._test_run_id else "none"
        if message is None:
            if self._test_run_saved:
                message = "complete ZIP saved"
            elif self._test_run_finalized:
                message = "finished; ZIP can be retried"
            elif self.cleaned_cloud is not None:
                message = "review ready; save the complete ZIP last"
            else:
                message = "recording"
        self.test_run_status.setText(f"Test run {run_short} • {message}")
        # Once diagnostics are finalized, freeze every workflow control so a
        # retry cannot silently package state that differs from the sealed run.
        # The persistent run toolbar remains available for ZIP retry/new run.
        self.navigation.setEnabled(not self._test_run_finalized)
        self.stack.setEnabled(not self._test_run_finalized)
        self.save_complete_run_button.setEnabled(
            self._test_run_id is not None and not self._test_run_saved
        )

    def _test_run_summary(self) -> dict[str, object]:
        final_points = len(self.cleaned_cloud.points) if self.cleaned_cloud is not None else 0
        raw_fused_points = self._raw_fused_point_count or final_points
        return {
            "scan_operation_id": self._scan_operation_id,
            "accepted_frames": self.accumulator.accepted_frames,
            "rejected_frames": self.accumulator.rejected_frames,
            "raw_profile_points": sum(
                len(profile.points_world) for profile in self.accumulator.profiles
            ),
            "raw_fused_point_count": raw_fused_points,
            "final_point_count": final_points,
            "triangle_count": len(self.mesh.faces) if self.mesh is not None else 0,
            "scan_preview_source_points": self.scan_page.cloud.source_point_count,
            "scan_preview_displayed_points": self.scan_page.cloud.displayed_point_count,
            "review_preview_source_points": self.review_page.viewer.source_point_count,
            "review_preview_displayed_points": self.review_page.viewer.displayed_point_count,
            "rejection_reasons": dict(self._scan_rejection_counts),
            "scan_evidence": self._scan_evidence.summary(),
            "package_requests": [dict(item) for item in self._run_package_requests],
        }

    def _run_settings_snapshot(self) -> dict[str, object]:
        return {
            "camera": self.camera_details,
            "laser": settings_dict(self.current_laser_settings()),
            "scan": settings_dict(self.current_scan_settings()),
            "preview": {
                "color_mode": self.scan_page.preview_colors.currentData(),
                "point_limit": self.scan_page.preview_points.currentData(),
                "display_only": True,
            },
            "background": {
                "available": self.background is not None,
                "age_s": self._background_age_s(),
                "statistics": (
                    self._frame_region_statistics(self.background)
                    if self.background is not None
                    else None
                ),
            },
        }

    def _discard_raw_fused_spool(self) -> None:
        holder = self._raw_fused_spool
        self._raw_fused_spool = None
        self._raw_fused_spool_path = None
        self._raw_fused_point_count = 0
        if holder is not None:
            try:
                holder.cleanup()
            except OSError as error:
                self.diagnostics.event(
                    "raw_fused_spool_cleanup_failed", failure=error
                )

    def _ensure_raw_fused_spool(self, cloud: PointCloud) -> None:
        """Persist the pre-cleanup fused cloud once, avoiding later re-fusion."""

        if self._raw_fused_spool_path is not None and self._raw_fused_spool_path.is_file():
            return
        holder = tempfile.TemporaryDirectory(prefix="laserline3d-raw-fused-")
        path = Path(holder.name) / "fused-scan.ply"
        try:
            export_point_cloud_ply(path, cloud)
        except Exception:
            holder.cleanup()
            raise
        self._discard_raw_fused_spool()
        self._raw_fused_spool = holder
        self._raw_fused_spool_path = path
        self._raw_fused_point_count = len(cloud.points)
        self.diagnostics.event(
            "raw_fused_cloud_spooled",
            state="preserved_for_complete_run",
            result="ok",
            point_count=self._raw_fused_point_count,
            size_bytes=path.stat().st_size,
        )

    def _start_test_run(self, *, initial: bool = False) -> None:
        self._test_run_id = self.diagnostics.start_test_run()
        self._test_run_finalized = False
        self._test_run_saved = False
        self._run_exported_artifacts.clear()
        self._run_package_requests.clear()
        self._test_run_end_frame = None
        self._test_run_frozen_settings = None
        self._update_test_run_status("recording from application start" if initial else "recording")

    def _has_unsaved_test_evidence(self) -> bool:
        return bool(
            not self._test_run_saved
            and (
                self.accumulator.accepted_frames
                or self.accumulator.rejected_frames
                or self.cleaned_cloud is not None
                or self._run_exported_artifacts
                or self._run_package_requests
            )
        )

    def start_new_test_run(self) -> None:
        """Begin an isolated physical test without discarding reusable calibration."""

        has_unsaved_evidence = self._has_unsaved_test_evidence()
        if has_unsaved_evidence:
            answer = QMessageBox.question(
                self,
                "Start a new test run?",
                "The current test has not been saved as a complete ZIP. Starting a new run clears its scan data. "
                "Reusable lens/corner calibration and the current laser-off background stay available.\n\n"
                "Start a new run anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        if self.scanning:
            self.pause_scan()
        previous_summary = self._test_run_summary()
        # Clear while the old run is still active so the discarded measurements
        # and operation ID are recorded under the correct correlation ID.
        self.clear_scan()
        if self._test_run_id is not None and not self._test_run_finalized:
            self.diagnostics.finish_test_run(
                status="cancelled", summary=previous_summary
            )
        self._start_test_run()
        self.navigation.setCurrentRow(4 if self.background is None else 5)
        self.scan_page.guidance.setText(
            "New test run started. Recapture the laser-off background if the object, lighting, exposure, or white balance changed."
        )

    def eventFilter(self, watched: object, event: object) -> bool:  # noqa: N802 - Qt API
        """Record in-app interaction structure without recording what was typed.

        A key event is represented by a safe category (navigation, activation,
        editing, or printable/other), modifiers, and the target widget class.
        The event's text and the contents of input widgets are never read.
        """

        try:
            if not isinstance(watched, QWidget) or not (
                watched is self or self.isAncestorOf(watched)
            ):
                return super().eventFilter(watched, event)  # type: ignore[arg-type]
            event_type = event.type()  # type: ignore[attr-defined]
            target = {
                "widget_class": watched.metaObject().className(),
                "object_name": watched.objectName() or None,
                "workflow_page": (
                    self.PAGE_NAMES[self.stack.currentIndex()]
                    if 0 <= self.stack.currentIndex() < len(self.PAGE_NAMES)
                    else None
                ),
            }
            if event_type == QEvent.Type.KeyPress:
                key = int(event.key())  # type: ignore[attr-defined]
                self.diagnostics.event(
                    "ui_key_press",
                    action="In-app key press",
                    state="observed",
                    result="recorded_without_text",
                    key_category=_safe_key_category(key),
                    modifiers=_safe_modifiers(event.modifiers()),  # type: ignore[attr-defined]
                    auto_repeat=bool(event.isAutoRepeat()),  # type: ignore[attr-defined]
                    **target,
                )
            elif event_type == QEvent.Type.MouseButtonRelease:
                position = event.position()  # type: ignore[attr-defined]
                width, height = max(1, watched.width()), max(1, watched.height())
                self.diagnostics.event(
                    "ui_mouse_click",
                    action="In-app mouse click",
                    state="observed",
                    result="recorded",
                    button=_safe_mouse_button(event.button()),  # type: ignore[attr-defined]
                    normalized_position=[
                        round(float(position.x()) / width, 4),
                        round(float(position.y()) / height, 4),
                    ],
                    **target,
                )
            elif event_type == QEvent.Type.Wheel:
                delta = event.angleDelta()  # type: ignore[attr-defined]
                self.diagnostics.event(
                    "ui_wheel",
                    action="In-app mouse wheel",
                    state="observed",
                    result="recorded",
                    horizontal_steps=float(delta.x()) / 120.0,
                    vertical_steps=float(delta.y()) / 120.0,
                    modifiers=_safe_modifiers(event.modifiers()),  # type: ignore[attr-defined]
                    **target,
                )
        except (AttributeError, RuntimeError, TypeError, ValueError):
            # Diagnostics must never interfere with the user's input path.
            pass
        return super().eventFilter(watched, event)  # type: ignore[arg-type]

    def _page_changed(self, index: int) -> None:
        if index != 5 and self.scanning:
            self.pause_scan()
        if 0 <= index < len(self.PAGE_NAMES):
            self.diagnostics.event(
                "workflow_page_changed",
                state=self.PAGE_NAMES[index],
                result="ok",
                page_index=index,
            )

    def on_preview_mode_changed(self, mode: str) -> None:
        self.diagnostics.event(
            "point_cloud_preview_mode_changed",
            action="Change 3D preview colors",
            state=mode,
            result="display_only",
            export_colors_changed=False,
        )

    def _log_corner_interaction(self, payload: object) -> None:
        details = dict(payload) if isinstance(payload, dict) else {"payload_type": type(payload).__name__}
        self.diagnostics.event(
            "corner_canvas_interaction",
            action=str(details.pop("action", "canvas_interaction")),
            state="corner_calibration",
            result="ok",
            **details,
        )

    def _current_camera_signal(self) -> bool:
        """Reject callbacks already queued by a disconnected/replaced camera."""

        sender = self.sender()
        if sender is None:
            # Direct method calls are used by focused UI tests.
            return True
        return bool(
            sender is self.camera_worker
            and getattr(sender, "camera_generation", None) == self._camera_generation
        )

    def _reset_camera_frame_state(self) -> None:
        self.latest_frame = None
        self.latest_timestamp = 0.0
        self.latest_sequence = 0
        self._background_sum = None
        self._background_remaining = 0

    def _request_camera_snapshot(self, context: str) -> bool:
        """Request one driver-property sample and label why it was requested."""

        if self.camera_worker is None:
            return False
        if self._camera_snapshot_pending is not None:
            self.diagnostics.event(
                "camera_property_snapshot_coalesced",
                state="pending",
                result="skipped_duplicate_request",
                requested_context=context,
                pending_context=self._camera_snapshot_pending,
            )
            return False
        self._camera_snapshot_pending = context
        self.camera_worker.request_property_snapshot()
        self.diagnostics.event(
            "camera_property_snapshot_requested",
            request="Read camera driver properties",
            state="pending",
            result="requested",
            context=context,
        )
        return True

    def _request_periodic_camera_snapshot(self) -> None:
        if self.scanning:
            self._request_camera_snapshot("periodic_during_scan")

    def _frame_region_statistics(self, image: np.ndarray) -> dict[str, object]:
        """Summarize the full image plus pixels inside/outside the green ROI."""

        evidence: dict[str, object] = {"full_frame": frame_statistics(image)}
        corner = self.corner_calibration
        if corner is None:
            return evidence
        height, width = image.shape[:2]
        x, y, roi_width, roi_height = (int(value) for value in corner.object_roi)
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(width, x + roi_width), min(height, y + roi_height)
        if x1 <= x0 or y1 <= y0:
            evidence["object_roi"] = {"status": "outside_frame"}
            return evidence
        evidence["object_roi"] = frame_statistics(image[y0:y1, x0:x1])
        outside_mask = np.ones((height, width), dtype=bool)
        outside_mask[y0:y1, x0:x1] = False
        outside_pixels = image[outside_mask]
        if len(outside_pixels):
            # Percentiles/color/clipping remain meaningful after flattening.
            # Spatial sharpness does not, so remove it explicitly.
            outside = frame_statistics(outside_pixels.reshape(-1, 1, 3))
            outside.pop("sharpness", None)
            outside["spatial_sharpness"] = "not_applicable_to_flattened_outside_roi_pixels"
            evidence["outside_object_roi"] = outside
        evidence["roi_px"] = [x0, y0, x1 - x0, y1 - y0]
        return evidence

    def _log_frame_statistics(
        self,
        context: str,
        *,
        image: np.ndarray | None = None,
        force: bool = False,
    ) -> bool:
        frame = self.latest_frame if image is None else image
        if frame is None:
            return False
        now = time.monotonic()
        interval = 5.0 if (self.scanning or self.stack.currentIndex() == 4) else 15.0
        if not force and now - self._last_frame_statistics_time < interval:
            return False
        self._last_frame_statistics_time = now
        try:
            evidence = self._frame_region_statistics(frame)
        except (TypeError, ValueError, cv2.error) as error:
            self.diagnostics.event(
                "camera_frame_statistics_failed",
                state=context,
                result="failed",
                failure=error,
            )
            return False
        self.diagnostics.event(
            "camera_frame_statistics",
            state=context,
            result="ok",
            sequence=int(self.latest_sequence),
            statistics=evidence,
        )
        return True

    def _invalidate_laser_background(self, reason: str) -> bool:
        invalidated = bool(
            self.background is not None
            or self._background_sum is not None
            or self._background_remaining > 0
        )
        self.background = None
        self._background_captured_monotonic = 0.0
        self._background_sum = None
        self._background_remaining = 0
        if invalidated:
            self.tune_page.background_status.setText(reason)
        return invalidated

    def connect_camera(self, request: CameraRequest) -> None:
        if not self.disconnect_camera():
            self._error(
                "Camera still stopping",
                "The previous camera did not stop yet. Wait a moment, then connect again.",
            )
            return
        self.diagnostics.event(
            "camera_connect_requested",
            action="Connect camera",
            request="Open USB camera",
            state="connecting",
            camera_index=request.index,
            backend=request.backend,
            resolution=[request.width, request.height],
            fps=request.fps,
            pixel_format=request.pixel_format or "driver_default",
        )
        worker = CameraWorker(request)
        worker.camera_generation = self._camera_generation
        worker.frame_ready.connect(self.on_camera_frame)
        worker.camera_opened.connect(self.on_camera_opened)
        worker.properties_reported.connect(self.on_camera_properties_reported)
        worker.camera_error.connect(self.on_camera_error)
        worker.camera_closed.connect(self.on_camera_closed)
        self.camera_worker = worker
        self.camera_page.status.set_status("Connecting…", "warning")
        worker.start()

    def disconnect_camera(self) -> bool:
        self.pause_scan()
        self._camera_generation += 1
        worker = self.camera_worker
        was_connected = worker is not None
        if worker is not None and worker.isRunning():
            worker.request_stop()
            if not worker.wait(2500):
                self._invalidate_laser_background(
                    "Camera is still stopping—capture a new laser-off background after reconnecting"
                )
                self._reset_camera_frame_state()
                self.camera_page.set_disconnected("Camera is still stopping…")
                self.diagnostics.event(
                    "camera_stop_timeout",
                    state="stopping",
                    result="failed",
                    failure="Camera worker did not stop within 2.5 seconds",
                )
                return False
        self.camera_worker = None
        self._camera_snapshot_pending = None
        background_invalidated = self._invalidate_laser_background(
            "Camera disconnected—capture a new laser-off background after reconnecting"
        )
        self._reset_camera_frame_state()
        self.camera_details = None
        self.camera_page.set_disconnected()
        if was_connected:
            self.diagnostics.event(
                "camera_disconnected",
                action="Disconnect camera",
                state="disconnected",
                result="ok",
                background_invalidated=background_invalidated,
            )
        return True

    def on_camera_opened(self, details: object) -> None:
        if not self._current_camera_signal():
            return
        opened = dict(details)  # type: ignore[arg-type]
        previous = self._last_camera_details
        identity_changed: dict[str, list[object]] = {}
        property_changed: dict[str, list[object]] = {}
        if previous is not None:
            for name in ("index", "backend", "width", "height"):
                if previous.get(name) != opened.get(name):
                    identity_changed[name] = [previous.get(name), opened.get(name)]
            old_properties = previous.get("properties")
            new_properties = opened.get("properties")
            if isinstance(old_properties, dict) and isinstance(new_properties, dict):
                for name in ("Autofocus", "Focus", "Zoom"):
                    if name not in old_properties or name not in new_properties:
                        continue
                    try:
                        same = bool(
                            np.isclose(
                                float(old_properties[name]),
                                float(new_properties[name]),
                                rtol=0.0,
                                atol=1e-6,
                                equal_nan=True,
                            )
                        )
                    except (TypeError, ValueError):
                        same = old_properties[name] == new_properties[name]
                    if not same:
                        property_changed[name] = [
                            old_properties[name],
                            new_properties[name],
                        ]
        resolution_mismatch = bool(
            self.camera_calibration is not None
            and self.camera_calibration.image_size
            != (int(opened.get("width", 0)), int(opened.get("height", 0)))
        )
        calibration_invalidated = bool(
            (identity_changed or property_changed or resolution_mismatch)
            and (self.camera_calibration is not None or self.corner_calibration is not None)
        )
        if calibration_invalidated:
            self.camera_calibration = None
            self.corner_calibration = None
            self.reconstructor = None
            self.lens_page.count.set_status(
                "Camera identity, resolution, focus, or zoom changed—repeat lens and corner calibration",
                "bad",
            )
            self._error(
                "Camera geometry changed",
                "The camera, backend, resolution, focus, autofocus, or zoom differs from the previous setup. Repeat lens calibration and the corner setup before scanning.",
            )
        opened_properties = opened.get("properties")
        safe_opened_properties = (
            dict(opened_properties) if isinstance(opened_properties, dict) else {}
        )
        self.camera_details = opened
        self._last_camera_details = {
            **opened,
            "properties": safe_opened_properties,
        }
        self.camera_page.set_connected(self.camera_details)
        negotiation = self.camera_details.get("mode_negotiation")
        if isinstance(negotiation, dict):
            mismatches = negotiation.get("mismatches")
            unverified = negotiation.get("unverified")
            result = "accepted"
            if isinstance(mismatches, dict) and mismatches:
                result = "substituted"
            elif isinstance(unverified, list) and unverified:
                result = "unverified"
            self.diagnostics.event(
                "camera_mode_negotiated",
                request="Apply requested camera resolution, frame rate, and USB video format",
                state="camera_ready",
                result=result,
                **negotiation,
            )
        self.diagnostics.event(
            "camera_opened",
            state="camera_ready",
            result="ok",
            identity_changed=identity_changed,
            geometric_properties_changed=property_changed,
            calibration_invalidated=calibration_invalidated,
            **self.camera_details,
        )

    def on_camera_closed(self) -> None:
        if not self._current_camera_signal():
            return
        self._reset_camera_frame_state()
        self.camera_details = None
        self.camera_page.set_disconnected()
        self.diagnostics.event("camera_closed", state="disconnected", result="ok")

    def on_camera_error(self, message: str) -> None:
        if not self._current_camera_signal():
            return
        self.scanning = False
        self._reset_camera_frame_state()
        self.camera_details = None
        self.camera_page.set_disconnected(f"Error: {message}")
        self.scan_page.set_scan_state(
            "error", has_data=bool(self.accumulator.accepted_frames)
        )
        self.diagnostics.event(
            "camera_failure", state="disconnected", result="failed", failure=message
        )
        self._error("Camera problem", message)

    def open_native_camera_settings(self) -> None:
        if self.camera_worker is None:
            self._error("Camera not connected", "Connect the camera first.")
            return
        self.camera_worker.open_native_settings()
        self._camera_snapshot_pending = "after_native_camera_settings"
        self.diagnostics.event(
            "camera_driver_settings_requested",
            action="Camera driver settings",
            request="Open native camera controls",
        )

    def refresh_camera_properties(self) -> None:
        if self.camera_worker is None:
            self._error("Camera not connected", "Connect the camera first.")
            return
        self._request_camera_snapshot("manual_refresh")

    def on_camera_properties_reported(self, properties: object) -> None:
        if not self._current_camera_signal():
            return
        context = self._camera_snapshot_pending or "camera_open_or_unsolicited"
        self._camera_snapshot_pending = None
        reported = dict(properties)  # type: ignore[arg-type]
        property_evidence = describe_camera_properties(reported)
        previous: dict[str, object] = {}
        if self.camera_details is not None:
            old = self.camera_details.get("properties")
            if isinstance(old, dict):
                previous = dict(old)
            self.camera_details["properties"] = reported
            self.camera_details["property_evidence"] = property_evidence
            self._last_camera_details = {
                **self.camera_details,
                "properties": dict(reported),
            }
        changed: dict[str, list[object]] = {}
        for name, value in reported.items():
            if name not in previous:
                continue
            try:
                same = bool(
                    np.isclose(
                        float(previous[name]), float(value), rtol=0.0, atol=1e-6, equal_nan=True
                    )
                )
            except (TypeError, ValueError):
                same = previous[name] == value
            if not same:
                changed[name] = [previous[name], value]
        background_invalidated = False
        calibration_invalidated = False
        appearance_controls = {
            "Auto exposure",
            "Exposure",
            "Gain",
            "Brightness",
            "Contrast",
            "Saturation",
            "Hue",
            "Gamma",
            "Sharpness",
            "Backlight compensation",
            "Auto white balance",
            "White balance temperature",
            "Iris",
            "Autofocus",
            "Focus",
            "Zoom",
        }
        appearance_changed = {
            name: values for name, values in changed.items() if name in appearance_controls
        }
        if appearance_changed:
            background_invalidated = self._invalidate_laser_background(
                "Camera controls changed—capture a new laser-off background"
            )
            geometric_controls = {"Autofocus", "Focus", "Zoom"}
            calibration_invalidated = bool(geometric_controls.intersection(appearance_changed)) and (
                self.camera_calibration is not None or self.corner_calibration is not None
            )
            if calibration_invalidated:
                self.camera_calibration = None
                self.corner_calibration = None
                self.reconstructor = None
                self.lens_page.count.set_status(
                    "Focus/autofocus/zoom changed—lens and corner calibration must be repeated",
                    "bad",
                )
                self._error(
                    "Camera geometry changed",
                    "Focus, autofocus, or zoom changed after calibration. Repeat lens calibration and the corner setup before scanning.",
                )
            if self.scanning:
                self.pause_scan()
                self.scan_page.guidance.setText(
                    "Camera exposure/color controls changed. A new laser-off background is required before scanning can resume."
                )
        self.camera_page.set_reported_properties(reported)
        self.diagnostics.event(
            "camera_properties_reported",
            state="camera_ready",
            result="ok",
            properties=reported,
            property_evidence=property_evidence,
            changed=changed,
            appearance_affecting_changed=appearance_changed,
            background_invalidated=background_invalidated,
            calibration_invalidated=calibration_invalidated,
            snapshot_context=context,
            note="Raw values; zero may also mean unsupported",
        )

    def on_camera_frame(self, frame: object, timestamp: float, sequence: int) -> None:
        if not self._current_camera_signal():
            return
        image = np.asarray(frame, dtype=np.uint8)
        self.latest_frame = image
        self.latest_timestamp = timestamp
        self.latest_sequence = sequence
        frame_context = (
            "background_capture"
            if self._background_remaining > 0
            else ("scanning" if self.scanning else self.PAGE_NAMES[self.stack.currentIndex()])
        )
        self._log_frame_statistics(frame_context, image=image)
        if self._background_remaining > 0:
            if self._background_sum is None:
                self._background_sum = image.astype(np.float64)
            else:
                self._background_sum += image
            self._background_remaining -= 1
            self.tune_page.background_status.setText(
                f"Capturing laser-off background… {15 - self._background_remaining}/15"
            )
            if self._background_remaining == 0 and self._background_sum is not None:
                self.background = np.rint(self._background_sum / 15.0).astype(np.uint8)
                self._background_captured_monotonic = time.monotonic()
                self._background_sum = None
                self.tune_page.background_status.setText("Background captured—turn the laser on")
                self.diagnostics.event(
                    "background_captured",
                    action="Capture 15 laser-off frames",
                    state="ready_for_laser",
                    result="ok",
                    frames=15,
                    background_age_s=0.0,
                    resolution=[int(self.background.shape[1]), int(self.background.shape[0])],
                    channel_means_bgr=np.mean(self.background, axis=(0, 1)).round(2).tolist(),
                    channel_min_bgr=np.min(self.background, axis=(0, 1)).tolist(),
                    channel_max_bgr=np.max(self.background, axis=(0, 1)).tolist(),
                    statistics=self._frame_region_statistics(self.background),
                )
                self._request_camera_snapshot("after_background_capture")
        page = self.stack.currentIndex()
        if page == 1:
            self.camera_page.canvas.set_frame(image)
        elif page == 2:
            self.lens_page.canvas.set_frame(image)
        elif page == 3 and self.rig_page.frozen_frame is None:
            self.rig_page.canvas.set_frame(image)
        elif page == 4:
            self.update_tuning_preview(image, timestamp, sequence)
        elif page == 5:
            if self.scanning and self.processing_worker is not None:
                interval = self.current_scan_settings().capture_interval_ms / 1000.0
                if timestamp - self._last_submit_time >= interval:
                    self.processing_worker.submit(
                        FramePacket(image.copy(), timestamp, sequence)
                    )
                    self._last_submit_time = timestamp
            elif self.reconstructor is not None:
                self.scan_page.canvas.set_frame(
                    image,
                    polygons=[
                        self.reconstructor.left_polygon,
                        self.reconstructor.right_polygon,
                    ],
                    roi=self.corner_calibration.object_roi if self.corner_calibration else None,
                )

    def capture_calibration_view(self) -> None:
        if self.latest_frame is None:
            self._error("No camera image", "Connect the camera and wait for a live image.")
            return
        requested = (
            self.lens_page.columns.value(),
            self.lens_page.rows.value(),
        )
        square = self.lens_page.square.value()
        if self.calibrator is None:
            self.calibrator = ChessboardCalibrator(requested, square)
        elif (
            self.calibrator.inner_corners != requested
            or self.calibrator.square_size_mm != square
        ):
            if self.calibrator.captures:
                self._error(
                    "Pattern changed",
                    "Reset the captured views before changing the chessboard dimensions.",
                )
                return
            self.calibrator = ChessboardCalibrator(requested, square)
        accepted, message, corners = self.calibrator.add_frame(self.latest_frame)
        count = len(self.calibrator.captures)
        self.lens_page.count.set_status(
            f"{count} accepted; 12 minimum",
            "good" if count >= 12 else "warning",
        )
        self.lens_page.message.setText(message)
        if corners is not None:
            overlay = self.latest_frame.copy()
            cv2.drawChessboardCorners(overlay, requested, corners, True)
            self.lens_page.canvas.set_frame(overlay)
        self.diagnostics.event(
            "calibration_view",
            action="Capture chessboard view",
            result="accepted" if accepted else "rejected",
            reason=message,
            accepted_count=count,
            frame_statistics=frame_statistics(self.latest_frame),
        )

    def reset_calibration_views(self) -> None:
        self.calibrator = None
        self.lens_page.count.set_status("0 accepted; 12 minimum", "neutral")
        self.lens_page.message.setText("Captured calibration views were cleared.")
        self.diagnostics.event(
            "calibration_views_cleared",
            action="Reset captured checkerboard views",
            state="camera_not_calibrated",
            result="ok",
        )

    def calculate_camera_calibration(self) -> None:
        if self.calibrator is None:
            self._error("No calibration views", "Capture at least 12 chessboard views first.")
            return
        try:
            calibration = self.calibrator.calibrate(minimum_views=12)
        except Exception as error:
            self._error("Calibration failed", str(error))
            self.diagnostics.event("camera_calibration_failed", failure=error)
            return
        path_text, _ = QFileDialog.getSaveFileName(
            self,
            "Save camera calibration",
            str(self.app_data_directory() / "calibrations" / "camera.json"),
            "Calibration JSON (*.json)",
        )
        if path_text:
            save_camera_calibration(Path(path_text), calibration)
        self.camera_calibration = calibration
        self.corner_calibration = None
        self.reconstructor = None
        quality = "good" if calibration.mean_reprojection_error_px <= 1.0 else "warning"
        self.lens_page.count.set_status(
            f"Saved: {calibration.accepted_views} views • {calibration.mean_reprojection_error_px:.3f} px mean reprojection error",
            quality,
        )
        self.diagnostics.event(
            "camera_calibrated",
            result="ok",
            state="camera_calibrated",
            rms_px=calibration.rms_error,
            mean_reprojection_px=calibration.mean_reprojection_error_px,
            image_size=calibration.image_size,
        )
        self.navigation.setCurrentRow(3)

    def load_camera_dialog(self) -> None:
        path_text, _ = QFileDialog.getOpenFileName(
            self,
            "Load camera calibration",
            str(self.app_data_directory() / "calibrations"),
            "Calibration JSON (*.json)",
        )
        if not path_text:
            return
        try:
            self.camera_calibration = load_camera_calibration(Path(path_text))
            self.corner_calibration = None
            self.reconstructor = None
            cal = self.camera_calibration
            self.lens_page.count.set_status(
                f"Loaded {cal.image_size[0]} × {cal.image_size[1]} calibration • {cal.mean_reprojection_error_px:.3f} px",
                "good",
            )
            self.diagnostics.event("camera_calibration_loaded", result="ok", path=path_text)
        except Exception as error:
            self._error("Could not load calibration", str(error))

    def freeze_rig_image(self) -> None:
        if self.camera_calibration is None:
            self._error("Lens calibration required", "Complete or load the camera lens calibration first.")
            return
        if self.latest_frame is None:
            self._error("No camera image", "Connect the camera first.")
            return
        actual = (self.latest_frame.shape[1], self.latest_frame.shape[0])
        if actual != self.camera_calibration.image_size:
            self._error(
                "Resolution mismatch",
                f"The camera is {actual[0]} × {actual[1]}, but the loaded calibration is for "
                f"{self.camera_calibration.image_size[0]} × {self.camera_calibration.image_size[1]}.",
            )
            return
        self.rig_page.begin_clicking(self.latest_frame)
        self._log_frame_statistics("corner_landmark_frame", force=True)
        self.diagnostics.event(
            "corner_landmark_frame_frozen",
            action="Freeze view for six landmarks",
            state="awaiting_landmarks",
            result="ok",
            resolution=[int(actual[0]), int(actual[1])],
        )

    def solve_corner(self) -> None:
        if self.camera_calibration is None:
            self._error("Lens calibration required", "Load a camera calibration first.")
            return
        if len(self.rig_page.clicks) != 6:
            self._error("Six points required", "Click every prompted physical corner in order.")
            return
        try:
            corner = fit_corner_pose(
                np.asarray(self.rig_page.clicks),
                self.camera_calibration,
                self.rig_page.wing_width.value(),
                self.rig_page.height.value(),
                self.rig_page.angle.value(),
            )
        except Exception as error:
            self._error("Corner calibration failed", str(error))
            self.diagnostics.event("corner_calibration_failed", failure=error)
            return
        self.corner_calibration = corner
        self.rebuild_reconstructor()
        self.rig_page.prompt.set_status(
            f"Pose solved • {corner.pose_reprojection_error_px:.2f} px reprojection RMS",
            "good" if corner.pose_reprojection_error_px <= 2.0 else "warning",
        )
        self.rig_page.await_object_view()
        if self.rig_page.frozen_frame is not None and self.reconstructor is not None:
            self.rig_page.canvas.set_frame(
                self.rig_page.frozen_frame,
                polygons=[self.reconstructor.left_polygon, self.reconstructor.right_polygon],
                roi=corner.object_roi,
            )
            self.rig_page.canvas.set_landmarks(self.rig_page.clicks)
        self.diagnostics.event(
            "corner_calibrated",
            result="ok",
            state="rig_calibrated",
            reprojection_rms_px=corner.pose_reprojection_error_px,
            width_mm=corner.wing_width_mm,
            height_mm=corner.height_mm,
            angle_deg=corner.hinge_angle_deg,
            landmarks_image_px=self.rig_page.clicks,
            final_canvas_view=self.rig_page.canvas.view_state(),
        )

    def capture_object_view(self) -> None:
        if self.corner_calibration is None or self.reconstructor is None:
            self._error("Corner setup required", "Solve the six-point corner pose first.")
            return
        if self.latest_frame is None:
            self._error("No camera image", "Connect the camera and wait for a live image.")
            return
        self.rig_page.begin_roi(
            self.latest_frame,
            self.corner_calibration.object_roi,
            [self.reconstructor.left_polygon, self.reconstructor.right_polygon],
        )
        self.rig_page.prompt.set_status("Object view captured—draw the green scan box", "good")
        self._log_frame_statistics("object_roi_frame", force=True)
        self.diagnostics.event(
            "object_roi_frame", action="Capture object view", result="ok",
            initial_roi=self.corner_calibration.object_roi,
        )

    def save_corner_dialog(self) -> None:
        if self.corner_calibration is None:
            self._error("No corner setup", "Solve or load the corner setup first.")
            return
        if self.rig_page.roi is not None:
            self.corner_calibration.object_roi = self.rig_page.roi
            self.rebuild_reconstructor()
        path_text, _ = QFileDialog.getSaveFileName(
            self,
            "Save corner setup",
            str(self.app_data_directory() / "calibrations" / "corner.json"),
            "Calibration JSON (*.json)",
        )
        if path_text:
            save_corner_calibration(Path(path_text), self.corner_calibration)
            self.navigation.setCurrentRow(4)

    def load_corner_dialog(self) -> None:
        if self.camera_calibration is None:
            self._error("Lens calibration required", "Load the matching camera calibration first.")
            return
        path_text, _ = QFileDialog.getOpenFileName(
            self,
            "Load reference-corner setup",
            str(self.app_data_directory() / "calibrations"),
            "Calibration JSON (*.json)",
        )
        if not path_text:
            return
        try:
            self.corner_calibration = load_corner_calibration(Path(path_text))
            self.rig_page.roi = self.corner_calibration.object_roi
            self.rebuild_reconstructor()
            self.rig_page.prompt.set_status("Corner setup loaded", "good")
            self.diagnostics.event("corner_calibration_loaded", result="ok", path=path_text)
        except Exception as error:
            self._error("Could not load corner setup", str(error))

    def capture_background(self) -> None:
        if self.latest_frame is None:
            self._error("No camera image", "Connect the camera first.")
            return
        if self.corner_calibration is None:
            self._error("Corner setup required", "Complete the reference-corner step first.")
            return
        self._background_sum = None
        self._background_remaining = 15
        self._request_camera_snapshot("before_background_capture")
        self._log_frame_statistics("before_background_capture_laser_off", force=True)
        self.tune_page.background_status.setText("Keep the laser OFF and the scene still…")
        self.diagnostics.event(
            "background_capture_started",
            action="Capture 15 laser-off frames",
            state="capturing",
            room_lighting_instruction="unchanged from scan",
            laser="off",
            frames_requested=15,
        )

    def _laser_settings_changed(self) -> None:
        self.rebuild_reconstructor()
        self._laser_log_timer.start()

    def _log_laser_settings(self) -> None:
        settings = self.current_laser_settings()
        self.diagnostics.event(
            "laser_settings_changed",
            action="Adjust laser detection control",
            state="tuning",
            result="applied",
            **settings_dict(settings),
        )

    def _laser_defaults_restored(self) -> None:
        self.diagnostics.event(
            "laser_defaults_restored",
            action="Restore defaults",
            state="tuning",
            result="ok",
            **settings_dict(self.current_laser_settings()),
        )

    def auto_suggest_laser_settings(self) -> None:
        if self.latest_frame is None:
            self._error("No camera image", "Connect the camera and wait for a live image.")
            return
        if self.background is None:
            self._error(
                "Laser-off background required",
                "Turn only the laser off, capture the 15-frame background, then turn it on.",
            )
            return
        self.rebuild_reconstructor()
        if self.reconstructor is None or self.corner_calibration is None:
            self._error("Calibration required", "Complete lens and corner calibration first.")
            return
        mask = np.zeros(self.latest_frame.shape[:2], dtype=np.uint8)
        for polygon in (
            self.reconstructor.left_polygon,
            self.reconstructor.right_polygon,
        ):
            points = np.rint(polygon).astype(np.int32)
            cv2.fillConvexPoly(mask, points, 1)
        x, y, width, height = self.corner_calibration.object_roi
        cv2.rectangle(mask, (x, y), (x + width, y + height), 1, -1)
        try:
            suggestion = suggest_laser_settings(
                self.latest_frame, self.background, mask.astype(bool)
            )
            self.tune_page.apply_settings(suggestion.settings)
            self.tune_page.quality.set_status(
                "Suggested starting values applied. Verify that one thin trace reaches both cyan wall regions and the green object region; adjust manually if needed.",
                "warning",
            )
            self.diagnostics.event(
                "laser_settings_auto_suggested",
                action="Auto-suggest from laser-on view",
                state="tuning",
                result="ok",
                noise_score=suggestion.noise_score,
                laser_score=suggestion.laser_score,
                separation=suggestion.separation,
                median_background_change=suggestion.median_background_change,
                sampled_pixels=suggestion.sampled_pixels,
                recommended=settings_dict(suggestion.settings),
                frame_statistics=self._frame_region_statistics(self.latest_frame),
            )
        except Exception as error:
            self.tune_page.quality.set_status(str(error), "bad")
            self.diagnostics.event(
                "laser_settings_auto_suggest_failed",
                action="Auto-suggest from laser-on view",
                failure=error,
            )
            self._error("Could not auto-suggest", str(error))

    def current_laser_settings(self) -> LaserSettings:
        return LaserSettings(
            minimum_red=self.tune_page.minimum_red.value(),
            minimum_dominance=self.tune_page.dominance.value(),
            threshold=float(self.tune_page.threshold.value()),
            orientation="horizontal",
            use_background=True,
        )

    def current_scan_settings(self) -> ScanSettings:
        return self._active_scan_settings

    def on_scan_density_preset_changed(self, preset_key: str) -> None:
        """Apply a density preset only before a scan owns any measurements."""

        if self.scanning or self.accumulator.accepted_frames:
            self.diagnostics.event(
                "scan_density_change_rejected",
                state="locked",
                result="ignored",
                requested_preset=preset_key,
                accepted_frames=self.accumulator.accepted_frames,
            )
            return
        settings = self.scan_page.selected_scan_settings()
        self._active_scan_settings = settings
        self.accumulator = ScanAccumulator(settings.voxel_size_mm, settings.max_points)
        self.rebuild_reconstructor()
        self.diagnostics.event(
            "scan_density_changed",
            action="Change point-cloud detail",
            state="ready",
            result="ok",
            preset=preset_key,
            scan_settings=settings_dict(settings),
        )

    def on_preview_point_limit_changed(self, point_limit: int) -> None:
        self.diagnostics.event(
            "point_cloud_preview_detail_changed",
            action="Change preview detail",
            state="display_only",
            result="ok",
            displayed_point_limit=int(point_limit),
            export_data_changed=False,
        )

    def rebuild_reconstructor(self) -> None:
        if self.corner_calibration is not None and self.rig_page.roi is not None:
            self.corner_calibration.object_roi = self.rig_page.roi
        if self.camera_calibration is None or self.corner_calibration is None:
            self.reconstructor = None
            return
        try:
            self.reconstructor = FrameReconstructor(
                self.camera_calibration,
                self.corner_calibration,
                self.current_laser_settings(),
                self.current_scan_settings(),
            )
        except Exception as error:
            self.reconstructor = None
            self.diagnostics.event("reconstructor_configuration_failed", failure=error)

    def _record_tune_readiness(
        self, result: object, *, background_drift: float | None, background_warning: bool
    ) -> None:
        quality = result.quality  # type: ignore[attr-defined]
        entry: dict[str, object] = {
            "time": time.monotonic(),
            "accepted": bool(quality.accepted),
            "reason_code": getattr(quality, "reason_code", None),
            "message": str(quality.message),
            "left_reference_points": int(quality.left_reference_points),
            "right_reference_points": int(quality.right_reference_points),
            "object_points": int(quality.object_points),
            "support_ratio": quality.support_ratio,
            "plane_rms_mm": quality.plane_rms_mm,
            "background_drift": background_drift,
            "background_warning": bool(background_warning),
        }
        self._latest_tune_result = result
        self._latest_tune_result_time = float(entry["time"])
        self._tune_readiness_history.append(entry)

    def _background_age_s(self) -> float | None:
        if self.background is None or self._background_captured_monotonic <= 0.0:
            return None
        return max(0.0, time.monotonic() - self._background_captured_monotonic)

    def _background_drift(self, image: np.ndarray) -> float | None:
        if self.background is None or self.background.shape != image.shape:
            return None
        # A deterministic spatial sample keeps the live check inexpensive.
        return float(
            np.median(
                np.abs(
                    image[::4, ::4].astype(np.int16)
                    - self.background[::4, ::4].astype(np.int16)
                )
            )
        )

    @staticmethod
    def _quality_evidence(quality: object) -> dict[str, object]:
        names = (
            "reason_code",
            "detected_points",
            "unclassified_points",
            "object_points",
            "left_reference_points",
            "right_reference_points",
            "valid_left_reference_points",
            "valid_right_reference_points",
            "plane_rms_mm",
            "support_ratio",
            "plane_inlier_count",
            "plane_left_inlier_count",
            "plane_right_inlier_count",
            "plane_median_residual_mm",
            "plane_covariance_eigenvalues_mm2",
            "plane_left_span_mm",
            "plane_right_span_mm",
            "plane_normal_uncertainty_deg",
            "triangulation_candidate_points",
            "ray_intersection_valid_points",
            "low_angle_rejected_points",
            "depth_rejected_points",
            "volume_rejected_points",
            "median_triangulation_angle_deg",
            "saturated_fraction",
        )
        return {name: getattr(quality, name, None) for name in names}

    def _scan_readiness_report(self) -> dict[str, object]:
        now = time.monotonic()
        recent = [
            entry
            for entry in self._tune_readiness_history
            if now - float(entry["time"]) <= 20.0
        ]
        latest = recent[-1] if recent else None
        issues: list[str] = []
        cautions: list[str] = []
        consecutive_accepted = 0
        for entry in reversed(recent):
            if not bool(entry["accepted"]):
                break
            consecutive_accepted += 1
        if latest is None:
            issues.append(
                "No recent Tune laser result is available. Return to Tune laser and hold one clean stripe across both cyan wall regions and the green object box."
            )
        else:
            if not bool(latest["accepted"]):
                issues.append(f"The latest preview was not triangulatable: {latest['message']}")
            if bool(latest["background_warning"]):
                issues.append("Lighting or camera exposure no longer matches the laser-off background.")
            if consecutive_accepted < 5:
                issues.append(
                    f"Reference lock is not stable yet ({consecutive_accepted} consecutive good frames; 5 required)."
                )
            support_ratio = latest.get("support_ratio")
            if support_ratio is None:
                issues.append("The latest preview has no measured laser-plane support margin.")
            elif float(support_ratio) < 0.006:
                cautions.append(
                    f"Reference support is close to the ambiguity guard ({float(support_ratio):.5f}; 0.00600 recommended)."
                )
        if self.corner_calibration is not None:
            reprojection = float(self.corner_calibration.pose_reprojection_error_px)
            if reprojection > 2.0:
                cautions.append(
                    f"Corner landmark reprojection error is {reprojection:.2f} px; 2.00 px or lower is recommended."
                )
        return {
            "ready": not issues and not cautions,
            "issues": issues,
            "cautions": cautions,
            "consecutive_accepted": consecutive_accepted,
            "recent_samples": len(recent),
            "latest": latest,
        }

    def _confirm_scan_readiness(self) -> bool:
        report = self._scan_readiness_report()
        if bool(report["ready"]):
            self.diagnostics.event(
                "scan_readiness_checked",
                state="ready",
                result="passed",
                **report,
            )
            return True
        lines = [str(value) for value in report["issues"]] + [
            str(value) for value in report["cautions"]
        ]
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Scan is not ready yet")
        box.setText("The live checks found conditions that can create holes or false points.")
        box.setInformativeText("\n\n".join(lines))
        return_button = box.addButton(
            "Return to Tune laser", QMessageBox.ButtonRole.RejectRole
        )
        override_button = box.addButton(
            "Start anyway (diagnostic run)", QMessageBox.ButtonRole.AcceptRole
        )
        box.setDefaultButton(return_button)
        box.exec()
        override = box.clickedButton() is override_button
        self.diagnostics.event(
            "scan_readiness_checked",
            action="Start anyway" if override else "Return to tuning",
            state="override" if override else "not_ready",
            result="user_override" if override else "cancelled",
            **report,
        )
        if not override:
            self.navigation.setCurrentRow(4)
        return override

    def update_tuning_preview(self, frame: np.ndarray, timestamp: float, sequence: int) -> None:
        if timestamp - self._tune_last_time < 0.10:
            return
        self._tune_last_time = timestamp
        self.rebuild_reconstructor()
        if self.reconstructor is None:
            self.tune_page.canvas.set_frame(frame)
            self.tune_page.quality.set_status("Complete lens and corner calibration", "bad")
            return
        try:
            result = self.reconstructor.process(
                frame,
                frame_index=sequence,
                timestamp_s=timestamp,
                background_bgr=self.background,
            )
            self.tune_page.canvas.set_frame(
                frame,
                points=result.detection.points,
                classes=result.point_classes,
                polygons=[self.reconstructor.left_polygon, self.reconstructor.right_polygon],
                roi=self.corner_calibration.object_roi if self.corner_calibration else None,
            )
            background_drift = self._background_drift(frame)
            background_warning = background_drift is not None and background_drift > 15.0
            level = (
                "bad"
                if background_warning
                else ("good" if result.quality.accepted else "warning")
            )
            prefix = (
                f"Lighting/exposure changed from the saved background (median {background_drift:.0f}); "
                "restore it or capture the laser-off background again. "
                if background_warning
                else ""
            )
            self.tune_page.quality.set_status(
                f"{prefix}{result.quality.message} • {len(result.detection.points)} stripe samples • "
                f"{result.detection.saturated_fraction * 100:.1f}% saturated • "
                f"left/right {result.quality.left_reference_points}/{result.quality.right_reference_points} • "
                f"support {result.quality.support_ratio:.5f}"
                if result.quality.support_ratio is not None
                else (
                    f"{prefix}{result.quality.message} • {len(result.detection.points)} stripe samples • "
                    f"{result.detection.saturated_fraction * 100:.1f}% saturated • "
                    f"left/right {result.quality.left_reference_points}/{result.quality.right_reference_points} • "
                    "support not available"
                ),
                level,
            )
            self._record_tune_readiness(
                result,
                background_drift=background_drift,
                background_warning=background_warning,
            )
            diagnostic_status = (
                f"{result.quality.accepted}:{result.quality.message}:"
                f"{len(result.detection.points)}:{result.quality.left_reference_points}:"
                f"{result.quality.right_reference_points}:{result.quality.object_points}"
            )
            if (
                timestamp - self._tune_diagnostic_time >= 1.0
                or diagnostic_status != self._tune_diagnostic_status
            ):
                self._tune_diagnostic_time = timestamp
                self._tune_diagnostic_status = diagnostic_status
                self.diagnostics.event(
                    "laser_tuning_preview",
                    state="accepted" if result.quality.accepted else "needs_adjustment",
                    result="ok",
                    message=result.quality.message,
                    median_background_change=background_drift,
                    background_mismatch=background_warning,
                    background_age_s=self._background_age_s(),
                    **self._quality_evidence(result.quality),
                    **settings_dict(self.current_laser_settings()),
                )
        except Exception as error:
            self.tune_page.quality.set_status(str(error), "bad")
            if timestamp - self._tune_diagnostic_time >= 1.0:
                self._tune_diagnostic_time = timestamp
                self.diagnostics.event("laser_tuning_preview_failed", failure=error)

    def _discard_processing_worker(self) -> None:
        """Stop a previous worker without allowing queued frames into a new scan."""

        worker = self.processing_worker
        if worker is None:
            return
        for signal, slot in (
            (worker.processed, self.on_processed_frame),
            (worker.processing_error, self.on_processing_error),
            (worker.finished, self.on_processing_finished),
        ):
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):
                pass
        worker.request_stop()
        stopped = worker.wait(3000)
        if stopped:
            if self.processing_worker is worker:
                self.processing_worker = None
        else:
            # Retain the QThread object until shutdown; deleting a running thread
            # can terminate the application. No more results are connected.
            self.processing_worker = worker
            self.diagnostics.event(
                "scan_worker_stop_timeout",
                state="discarding",
                failure="Processing worker did not stop within 3 seconds",
            )

    def start_scan(self) -> None:
        self.rebuild_reconstructor()
        if self.camera_worker is None or self.latest_frame is None:
            self._error("Camera required", "Connect the camera before scanning.")
            return
        if self.reconstructor is None:
            self._error("Calibration required", "Complete the lens and reference-corner setup first.")
            return
        if self.background is None:
            self._error("Background required", "Capture the scene with the laser off on the Tune laser step.")
            return
        if not self._confirm_scan_readiness():
            return
        self._request_camera_snapshot("scan_start")
        self._log_frame_statistics("scan_start", force=True)
        # A paused worker owns a frozen reconstructor/background and may still
        # contain queued frames. A fresh worker makes resume/clear deterministic.
        # Invalidate its generation before waiting so already-posted Qt signals
        # can never enter the current accumulator, even if shutdown times out.
        self._scan_generation += 1
        if self.processing_worker is not None:
            self._discard_processing_worker()
            if self.processing_worker is not None and self.processing_worker.isRunning():
                self._error("Scanner still stopping", "Wait a moment, then try Start scan again.")
                self.scan_page.set_scan_state(
                    "error", has_data=bool(self.accumulator.accepted_frames)
                )
                return
        worker = ProcessingWorker(self.reconstructor, self.background)
        worker.scan_generation = self._scan_generation
        worker.processed.connect(self.on_processed_frame)
        worker.processing_error.connect(self.on_processing_error)
        worker.finished.connect(self.on_processing_finished)
        self.processing_worker = worker
        worker.start()
        self.scanning = True
        self._no_line_streak = 0
        self._finish_pending = False
        self._last_submit_time = 0.0
        if self._scan_operation_id is None:
            self._scan_operation_id = str(uuid.uuid4())
        self.scan_page.set_scan_state(
            "scanning", has_data=bool(self.accumulator.accepted_frames)
        )
        self.scan_page.guidance.setText("Scanning—sweep the line slowly across the object.")
        self.diagnostics.event(
            "scan_started",
            action="Resume scan" if self.accumulator.accepted_frames else "Start scan",
            state="capturing",
            result="ok",
            operation_id=self._scan_operation_id,
            accepted_frames=self.accumulator.accepted_frames,
            rejected_frames=self.accumulator.rejected_frames,
            laser_settings=settings_dict(self.current_laser_settings()),
            scan_settings=settings_dict(self.current_scan_settings()),
            camera_properties=(self.camera_details or {}).get("properties"),
            background_age_s=self._background_age_s(),
            object_roi=(self.corner_calibration.object_roi if self.corner_calibration else None),
            corner_reprojection_rms_px=(
                self.corner_calibration.pose_reprojection_error_px
                if self.corner_calibration is not None
                else None
            ),
        )

    def pause_scan(self) -> None:
        if self.scanning:
            self.scanning = False
            self.scan_page.set_scan_state(
                "paused", has_data=bool(self.accumulator.accepted_frames)
            )
            self.scan_page.guidance.setText("Paused. Resume when ready; existing data is safe.")
            self.diagnostics.event(
                "scan_paused",
                action="Pause scan",
                state="paused",
                result="ok",
                operation_id=self._scan_operation_id,
            )
            self._request_camera_snapshot("scan_pause")
            self._log_frame_statistics("scan_pause", force=True)

    def finish_scan(self) -> None:
        worker_running = (
            self.processing_worker is not None and self.processing_worker.isRunning()
        )
        if (
            not self.scanning
            and not self._finish_pending
            and not worker_running
            and self.cleaned_cloud is not None
            and len(self.cleaned_cloud.points)
        ):
            # Finish is intentionally idempotent.  In 0.3.0, pressing it a
            # second time rebuilt the raw accumulator cloud and silently undid
            # cleanup.  Reuse the reviewed result until new frames arrive.
            self.review_page.set_model(self.cleaned_cloud, self.mesh)
            self.scan_page.set_scan_state("paused", has_data=True)
            self.navigation.setCurrentRow(6)
            self._update_test_run_status("review preserved; save the complete ZIP last")
            self.diagnostics.event(
                "scan_finish_reused_reviewed_result",
                action="Finish and review",
                state="review",
                result="ok",
                operation_id=self._scan_operation_id,
                point_count=len(self.cleaned_cloud.points),
                triangle_count=len(self.mesh.faces) if self.mesh is not None else 0,
                cleanup_preserved=True,
            )
            return
        self.scanning = False
        self._finish_pending = True
        self.scan_page.set_scan_state(
            "finishing", has_data=bool(self.accumulator.accepted_frames)
        )
        self.diagnostics.event(
            "scan_finish_requested",
            action="Finish and review",
            state="finishing",
            operation_id=self._scan_operation_id,
            accepted_frames=self.accumulator.accepted_frames,
            rejected_frames=self.accumulator.rejected_frames,
        )
        self._request_camera_snapshot("scan_finish")
        self._log_frame_statistics("scan_finish", force=True)
        if self.processing_worker is not None and self.processing_worker.isRunning():
            self.processing_worker.request_stop()
            self.scan_page.guidance.setText("Finishing queued frames…")
        else:
            self.on_processing_finished()

    def on_processing_finished(self) -> None:
        sender = self.sender()
        if (
            sender is not None
            and getattr(sender, "scan_generation", self._scan_generation)
            != self._scan_generation
        ):
            return
        if self.processing_worker is not None and not self.processing_worker.isRunning():
            self.processing_worker = None
        if not self._finish_pending:
            return
        self._finish_pending = False
        if self.cleaned_cloud is not None and len(self.cleaned_cloud.points):
            review_result_reused = True
            cloud = self.cleaned_cloud
        else:
            review_result_reused = False
            cloud = self.accumulator.cloud()
        if not len(cloud.points):
            self.scan_page.set_scan_state("ready", has_data=False)
            self.scan_page.guidance.setText(
                "No frames passed the checks. Review the message above, then try again."
            )
            self.diagnostics.event(
                "scan_finished_no_data",
                state="ready",
                result="no_accepted_frames",
                operation_id=self._scan_operation_id,
                accepted_frames=self.accumulator.accepted_frames,
                rejected_frames=self.accumulator.rejected_frames,
                rejection_reasons=dict(self._scan_rejection_counts),
                evidence=self._scan_evidence.summary(),
            )
            self._error("No scan data", "No frames passed the reference and geometry checks.")
            self._update_test_run_status("recording; no accepted scan frames")
            return
        self.cleaned_cloud = cloud
        if not review_result_reused:
            self._discard_raw_fused_spool()
            self._raw_fused_point_count = len(cloud.points)
            self._cloud_cleanup_applied = False
            self.mesh = None
        self.review_page.set_model(cloud, self.mesh)
        self.scan_page.set_scan_state("paused", has_data=True)
        self.navigation.setCurrentRow(6)
        self._update_test_run_status("review ready; save the complete ZIP last")
        self.diagnostics.event(
            "scan_finished",
            state="review",
            result="ok",
            operation_id=self._scan_operation_id,
            accepted_frames=self.accumulator.accepted_frames,
            rejected_frames=self.accumulator.rejected_frames,
            point_count=len(cloud.points),
            triangle_count=len(self.mesh.faces) if self.mesh is not None else 0,
            review_result_reused=review_result_reused,
            rejection_reasons=dict(self._scan_rejection_counts),
            evidence=self._scan_evidence.summary(),
        )

    def clear_scan(self) -> None:
        self.scanning = False
        self._finish_pending = False
        self._scan_generation += 1
        self._discard_processing_worker()
        previous_accepted = self.accumulator.accepted_frames
        previous_rejected = self.accumulator.rejected_frames
        previous_points = sum(len(profile.points_world) for profile in self.accumulator.profiles)
        previous_operation_id = self._scan_operation_id
        self._active_scan_settings = self.scan_page.selected_scan_settings()
        self.accumulator = ScanAccumulator(
            self._active_scan_settings.voxel_size_mm,
            self._active_scan_settings.max_points,
        )
        self.cleaned_cloud = None
        self.mesh = None
        self._discard_raw_fused_spool()
        self._cloud_cleanup_applied = False
        self._processed_frame_count = 0
        previous_reasons = dict(self._scan_rejection_counts)
        self._scan_rejection_counts.clear()
        self._scan_evidence = ScanEvidenceAccumulator()
        self._last_scan_detail_log_time = 0.0
        self._last_scan_reason_code = ""
        self._no_line_streak = 0
        self._scan_operation_id = None
        self.scan_page.cloud.set_cloud(None)
        self.review_page.set_model(None, None)
        self.scan_page.coverage.set_status("0 frames • 0 points", "neutral")
        self.scan_page.guidance.setText("Scan data cleared. Ready for a new sweep.")
        self.scan_page.mark_scan_cleared()
        self.diagnostics.event(
            "scan_cleared",
            action="Clear scan",
            state="ready",
            result="ok",
            operation_id=previous_operation_id,
            removed_accepted_frames=previous_accepted,
            removed_rejected_frames=previous_rejected,
            removed_points=previous_points,
            rejection_reasons=previous_reasons,
        )
        self._update_test_run_status("recording; scan data cleared")

    def on_processed_frame(self, result: object, frame: object) -> None:
        sender = self.sender()
        if (
            sender is not None
            and getattr(sender, "scan_generation", self._scan_generation)
            != self._scan_generation
        ):
            self.diagnostics.event(
                "stale_scan_frame_discarded", state="discarded", result="ok"
            )
            return
        processed = result
        image = np.asarray(frame, dtype=np.uint8)
        self._processed_frame_count += 1
        try:
            accepted = self.accumulator.add(processed)
        except Exception as error:
            self.pause_scan()
            self._error("Scan limit reached", str(error))
            return
        if accepted and (self.cleaned_cloud is not None or self.mesh is not None):
            previous_points = (
                len(self.cleaned_cloud.points) if self.cleaned_cloud is not None else 0
            )
            previous_triangles = len(self.mesh.faces) if self.mesh is not None else 0
            self.cleaned_cloud = None
            self.mesh = None
            self._discard_raw_fused_spool()
            self._cloud_cleanup_applied = False
            self.review_page.set_model(None, None)
            self.diagnostics.event(
                "scan_review_result_invalidated",
                state="capturing",
                result="ok",
                reason="new_accepted_frame",
                operation_id=self._scan_operation_id,
                previous_point_count=previous_points,
                previous_triangle_count=previous_triangles,
            )
        self.scan_page.canvas.set_frame(
            image,
            points=processed.detection.points,
            classes=processed.point_classes,
            polygons=[self.reconstructor.left_polygon, self.reconstructor.right_polygon] if self.reconstructor else [],
            roi=self.corner_calibration.object_roi if self.corner_calibration else None,
        )
        raw_count = sum(len(profile.points_world) for profile in self.accumulator.profiles)
        dropped = self.processing_worker.dropped_frames if self.processing_worker else 0
        self.scan_page.show_quality(
            processed.quality,
            self.accumulator.accepted_frames,
            raw_count,
            dropped,
        )
        background_drift = self._background_drift(image)
        background_warning = background_drift is not None and background_drift > 15.0
        if background_warning:
            self.scan_page.guidance.setText(
                f"Lighting/exposure differs from the laser-off background (median change {background_drift:.0f}). "
                "Pause, restore the camera/lighting, or capture a new background before trusting this scan."
            )
        if accepted and self.accumulator.accepted_frames % 5 == 0:
            self.scan_page.cloud.set_cloud(self.accumulator.cloud())
        quality = processed.quality
        self._record_tune_readiness(
            processed,
            background_drift=background_drift,
            background_warning=background_warning,
        )
        roi = self.corner_calibration.object_roi if self.corner_calibration else None
        frame_evidence = self._scan_evidence.add(processed, roi)
        reason_code = str(getattr(quality, "reason_code", quality.message))
        if reason_code in {"laser_not_detected", "insufficient_laser_points"}:
            self._no_line_streak += 1
        else:
            self._no_line_streak = 0
        if not accepted:
            self._scan_rejection_counts[reason_code] += 1
        now = time.monotonic()
        status_changed = reason_code != self._last_scan_reason_code
        should_log = (
            self._processed_frame_count == 1
            or now - self._last_scan_detail_log_time >= 1.0
            or (status_changed and now - self._last_scan_detail_log_time >= 0.25)
        )
        if should_log:
            self._last_scan_detail_log_time = now
            self._last_scan_reason_code = reason_code
            self.diagnostics.event(
                "scan_frame_sample",
                state="accepted" if accepted else "rejected",
                result="ok",
                operation_id=self._scan_operation_id,
                processed_frame=self._processed_frame_count,
                accepted=accepted,
                reason=quality.message,
                accumulated_accepted=self.accumulator.accepted_frames,
                accumulated_rejected=self.accumulator.rejected_frames,
                worker_dropped_frames=dropped,
                median_background_change=background_drift,
                background_mismatch=background_warning,
                background_age_s=self._background_age_s(),
                spatial_evidence=frame_evidence,
                **self._quality_evidence(quality),
            )
        if self.scanning and self._no_line_streak >= 50:
            self.pause_scan()
            self.scan_page.guidance.setText(
                "Scan paused after 50 consecutive frames without a usable laser line. "
                "Put the stripe back on both walls and the object, verify Tune laser, then resume."
            )
            self.diagnostics.event(
                "scan_auto_paused_no_line",
                state="paused",
                result="safety_watchdog",
                operation_id=self._scan_operation_id,
                consecutive_no_line_frames=self._no_line_streak,
            )

    def on_processing_error(self, message: str) -> None:
        sender = self.sender()
        if (
            sender is not None
            and getattr(sender, "scan_generation", self._scan_generation)
            != self._scan_generation
        ):
            return
        self.scanning = False
        self.scan_page.set_scan_state(
            "error", has_data=bool(self.accumulator.accepted_frames)
        )
        self.scan_page.guidance.setText(f"Processing stopped: {message}")
        self.diagnostics.event(
            "scan_processing_failure",
            state="error",
            result="failed",
            failure=message,
            operation_id=self._scan_operation_id,
        )

    def save_diagnostics_bundle(self) -> None:
        """Create a user-controlled ZIP with the session evidence needed for support."""

        if self.scanning:
            self.pause_scan()
        self._request_camera_snapshot("before_diagnostic_export")
        self._log_frame_statistics("before_diagnostic_export", force=True)
        include_images = QMessageBox.question(
            self,
            "Include camera images?",
            "The current camera frame and saved laser-off background are very useful for "
            "diagnosing laser bleed, lighting, and detection. They may show your room or "
            "object. Include those two images in the diagnostics ZIP?",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Yes,
        )
        if include_images == QMessageBox.StandardButton.Cancel:
            self.diagnostics.event(
                "support_bundle_cancelled", action="Save diagnostics ZIP", result="cancelled"
            )
            return
        documents = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
        suggested = Path(documents or str(Path.home())) / (
            f"LaserLine3D_diagnostics_{time.strftime('%Y%m%d_%H%M%S')}.zip"
        )
        path_text, _ = QFileDialog.getSaveFileName(
            self,
            "Save diagnostics ZIP",
            str(suggested),
            "ZIP archive (*.zip)",
        )
        if not path_text:
            self.diagnostics.event(
                "support_bundle_cancelled", action="Save diagnostics ZIP", result="cancelled"
            )
            return

        background_summary: dict[str, object] | None = None
        if self.background is not None:
            background_summary = {
                "resolution": [int(self.background.shape[1]), int(self.background.shape[0])],
                "channel_means_bgr": np.mean(self.background, axis=(0, 1)).round(2).tolist(),
                "channel_min_bgr": np.min(self.background, axis=(0, 1)).tolist(),
                "channel_max_bgr": np.max(self.background, axis=(0, 1)).tolist(),
                "age_s": self._background_age_s(),
                "statistics": self._frame_region_statistics(self.background),
            }
        metadata = {
            "application_version": __version__,
            "camera": self.camera_details,
            "camera_calibration": (
                self.camera_calibration.to_dict() if self.camera_calibration is not None else None
            ),
            "corner_calibration": (
                self.corner_calibration.to_dict() if self.corner_calibration is not None else None
            ),
            "laser_settings": settings_dict(self.current_laser_settings()),
            "scan_settings": settings_dict(self.current_scan_settings()),
            "scan": {
                "ui_state": self.scan_page.scan_state,
                "operation_id": self._scan_operation_id,
                "accepted_frames": self.accumulator.accepted_frames,
                "rejected_frames": self.accumulator.rejected_frames,
                "processed_frames_logged": self._processed_frame_count,
                "point_count": sum(
                    len(profile.points_world) for profile in self.accumulator.profiles
                ),
                "rejection_reasons": dict(self._scan_rejection_counts),
                "evidence": self._scan_evidence.summary(),
            },
            "laser_off_background": background_summary,
            "current_frame_statistics": (
                self._frame_region_statistics(self.latest_frame)
                if self.latest_frame is not None
                else None
            ),
        }

        try:
            with tempfile.TemporaryDirectory(prefix="laserline3d_support_") as temporary:
                attachments: dict[str, Path] = {}
                if include_images == QMessageBox.StandardButton.Yes:
                    temp_root = Path(temporary)
                    if self.latest_frame is not None:
                        live_path = temp_root / "current-camera-frame.jpg"
                        if cv2.imwrite(str(live_path), self.latest_frame):
                            attachments[live_path.name] = live_path
                    if self.background is not None:
                        background_path = temp_root / "laser-off-background.png"
                        if cv2.imwrite(str(background_path), self.background):
                            attachments[background_path.name] = background_path
                bundle = self.diagnostics.export_support_bundle(
                    Path(path_text), metadata=metadata, attachments=attachments
                )
            QMessageBox.information(
                self,
                "Diagnostics saved",
                f"Saved:\n{bundle}\n\nYou can upload this ZIP for troubleshooting. "
                "Review it before sharing if your camera scene is private.",
            )
        except Exception as error:
            self._error("Could not save diagnostics", str(error))

    def clean_cloud(self) -> None:
        source = self.cleaned_cloud or self.accumulator.cloud()
        if not len(source.points):
            self._error("No points", "Finish a scan or open a project first.")
            return
        self.diagnostics.event(
            "cloud_cleanup_requested",
            action="Remove isolated dots",
            state="processing",
            source_point_count=len(source.points),
        )
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            if not self._cloud_cleanup_applied:
                try:
                    self._ensure_raw_fused_spool(source)
                except Exception as error:
                    self.diagnostics.event(
                        "raw_fused_cloud_spool_failed",
                        failure=error,
                        point_count=len(source.points),
                    )
            cleaned = remove_statistical_outliers(source)
            removed = len(source.points) - len(cleaned.points)
            self.cleaned_cloud = cleaned
            self._cloud_cleanup_applied = True
            self.mesh = None
            self.review_page.set_model(cleaned, None)
            self.review_page.summary.set_status(
                f"{len(cleaned.points):,} points • removed {removed:,} isolated points • no surface yet",
                "good",
            )
            self.diagnostics.event(
                "cloud_cleaned",
                state="review",
                result="ok",
                source_point_count=len(source.points),
                retained_point_count=len(cleaned.points),
                removed_point_count=removed,
            )
        except Exception as error:
            self._error("Cleanup failed", str(error))
            self.diagnostics.event("cloud_cleanup_failed", failure=error)
        finally:
            QApplication.restoreOverrideCursor()

    def create_mesh(self) -> None:
        cloud = self.cleaned_cloud or self.accumulator.cloud()
        if not len(cloud.points):
            self._error("No points", "Finish a scan or open a project first.")
            return
        self.diagnostics.event(
            "mesh_creation_requested",
            action="Create surface mesh",
            state="processing",
            source_point_count=len(cloud.points),
        )
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.mesh = build_front_surface(cloud)
            self.cleaned_cloud = cloud
            self.review_page.set_model(cloud, self.mesh)
            self.diagnostics.event(
                "mesh_created", result="ok", triangle_count=len(self.mesh.faces)
            )
        except Exception as error:
            self._error("Surface creation failed", str(error))
            self.diagnostics.event("mesh_creation_failed", failure=error)
        finally:
            QApplication.restoreOverrideCursor()

    def save_project_dialog(self) -> None:
        if self.cleaned_cloud is None or self.camera_calibration is None or self.corner_calibration is None:
            self._error("Nothing to save", "Finish a calibrated scan first.")
            return
        path_text, _ = QFileDialog.getSaveFileName(
            self, "Save LaserLine project", "scan.llscan", "LaserLine scan (*.llscan)"
        )
        if not path_text:
            return
        path = Path(path_text)
        if path.suffix.lower() != ".llscan":
            path = path.with_suffix(".llscan")
        try:
            save_project(
                path,
                self.cleaned_cloud,
                self.camera_calibration,
                self.corner_calibration,
                name=path.stem,
                metadata={
                    "accepted_frames": self.accumulator.accepted_frames,
                    "rejected_frames": self.accumulator.rejected_frames,
                },
            )
            metadata_path = path.with_suffix(path.suffix + ".json")
            write_export_metadata(
                metadata_path,
                self._export_metadata("editable_project", stage="manual_project"),
            )
            self._track_run_export(path, metadata_path, "editable_project")
            self.diagnostics.event("project_saved", result="ok", path=str(path))
        except Exception as error:
            self._error("Could not save project", str(error))
            self.diagnostics.event("project_save_failed", failure=error)

    def open_project_dialog(self) -> None:
        path_text, _ = QFileDialog.getOpenFileName(
            self, "Open LaserLine project", "", "LaserLine scan (*.llscan)"
        )
        if not path_text:
            return
        try:
            cloud, camera, corner, _manifest = load_project(Path(path_text))
            self.camera_calibration = camera
            self.corner_calibration = corner
            self.rig_page.roi = corner.object_roi
            self.rebuild_reconstructor()
            self.cleaned_cloud = cloud
            self.mesh = None
            self._discard_raw_fused_spool()
            self._raw_fused_point_count = len(cloud.points)
            self._cloud_cleanup_applied = False
            self.review_page.set_model(cloud, None)
            self.navigation.setCurrentRow(6)
            self.diagnostics.event("project_opened", result="ok", path=path_text)
        except Exception as error:
            self._error("Could not open project", str(error))
            self.diagnostics.event("project_open_failed", failure=error)

    def _export_metadata(
        self,
        kind: str,
        *,
        cloud: PointCloud | None = None,
        mesh: Mesh | None = None,
        stage: str = "final",
    ) -> dict[str, object]:
        selected_cloud = self.cleaned_cloud if cloud is None else cloud
        selected_mesh = self.mesh if mesh is None and kind != "point_cloud" else mesh
        return {
            "artifact": kind,
            "stage": stage,
            "application_version": __version__,
            "application_session_id": self.diagnostics.session_id,
            "test_run_id": self._test_run_id,
            "scan_operation_id": self._scan_operation_id,
            "point_count": len(selected_cloud.points) if selected_cloud else 0,
            "triangle_count": len(selected_mesh.faces) if selected_mesh else 0,
            "mesh_is_watertight": (
                is_watertight(selected_mesh) if selected_mesh else False
            ),
            "warning": "Single-view measured surface; hidden backs are not present.",
        }

    def export_ply_dialog(self) -> None:
        if self.cleaned_cloud is None or not len(self.cleaned_cloud.points):
            self._error("No point cloud", "Finish a scan first.")
            return
        path_text, _ = QFileDialog.getSaveFileName(self, "Export PLY", "scan.ply", "PLY (*.ply)")
        if path_text:
            self._run_export(Path(path_text), export_point_cloud_ply, self.cleaned_cloud, "point_cloud")

    def export_obj_dialog(self) -> None:
        if self.mesh is None:
            return
        path_text, _ = QFileDialog.getSaveFileName(self, "Export OBJ", "scan.obj", "OBJ (*.obj)")
        if path_text:
            self._run_export(Path(path_text), export_obj, self.mesh, "surface_mesh")

    def export_stl_dialog(self) -> None:
        if self.mesh is None:
            return
        path_text, _ = QFileDialog.getSaveFileName(self, "Export STL", "scan.stl", "STL (*.stl)")
        if path_text:
            self._run_export(Path(path_text), export_binary_stl, self.mesh, "surface_mesh")

    def _track_run_export(self, path: Path, metadata_path: Path, kind: str) -> None:
        """Keep one honest registry entry per mutable destination path."""

        identity = str(path.resolve(strict=False)).casefold()
        for index, (existing, _metadata, _kind) in enumerate(
            self._run_exported_artifacts
        ):
            if str(existing.resolve(strict=False)).casefold() == identity:
                self._run_exported_artifacts[index] = (path, metadata_path, kind)
                self.diagnostics.event(
                    "run_manual_export_registry_replaced",
                    state="latest_file_at_destination",
                    result="ok",
                    destination_name=path.name,
                    artifact=kind,
                )
                return
        self._run_exported_artifacts.append((path, metadata_path, kind))

    def _run_export(self, path: Path, exporter: object, payload: object, kind: str) -> None:
        self._request_camera_snapshot(f"before_{kind}_export")
        self._log_frame_statistics(f"before_{kind}_export", force=True)
        self.diagnostics.event(
            "model_export_requested",
            action=f"Export {path.suffix.upper().lstrip('.')}",
            state="writing",
            artifact=kind,
            format=path.suffix,
            destination_name=path.name,
        )
        try:
            exporter(path, payload)  # type: ignore[operator]
            metadata_path = path.with_suffix(path.suffix + ".json")
            write_export_metadata(metadata_path, self._export_metadata(kind))
            self._track_run_export(path, metadata_path, kind)
            self.diagnostics.event("model_exported", result="ok", path=str(path), format=path.suffix)
            QMessageBox.information(self, "Export complete", f"Saved:\n{path}")
        except Exception as error:
            self._error("Export failed", str(error))
            self.diagnostics.event(
                "model_export_failed",
                failure=error,
                artifact=kind,
                format=path.suffix,
                destination_name=path.name,
            )

    def save_complete_test_run_bundle(self) -> None:
        """Seal one physical test into a single validated, uploadable ZIP."""

        run_id = self._test_run_id
        if run_id is None:
            self._error("No active test run", "Start a new test run first.")
            return
        if self._test_run_saved:
            self._error(
                "Test already saved",
                "Start a new test run before collecting another independent test.",
            )
            return
        worker_running = (
            self.processing_worker is not None and self.processing_worker.isRunning()
        )
        if self.scanning or self._finish_pending or worker_running:
            self._error(
                "Finish the scan first",
                "Press Finish and review, wait for queued frames to finish, then save the complete test ZIP.",
            )
            return
        if self.cleaned_cloud is None or not len(self.cleaned_cloud.points):
            self._error("No finished scan", "Finish a scan before saving the complete test ZIP.")
            return
        default_name = (
            "LaserLine3D_complete_run_"
            f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{run_id[:8]}.zip"
        )
        path_text, _ = QFileDialog.getSaveFileName(
            self,
            "Save complete physical test",
            default_name,
            "ZIP archive (*.zip)",
        )
        if not path_text:
            return
        image_choice = QMessageBox.question(
            self,
            "Include camera images?",
            "The complete ZIP always includes diagnostics and every scan format. Include the current camera frame and laser-off background too?\n\n"
            "Images may show your room or other private details. Review the ZIP before sharing.",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.No,
        )
        if image_choice == QMessageBox.StandardButton.Cancel:
            return
        include_images = image_choice == QMessageBox.StandardButton.Yes
        destination = Path(path_text)
        if destination.suffix.lower() != ".zip":
            destination = destination.with_suffix(".zip")
        if not self._test_run_finalized:
            self._test_run_end_frame = (
                self.latest_frame.copy() if self.latest_frame is not None else None
            )
            self._test_run_frozen_settings = self._run_settings_snapshot()
        package_request: dict[str, object] = {
            "attempt": len(self._run_package_requests) + 1,
            "requested_utc": datetime.now().astimezone().isoformat(),
            "destination_name": destination.name,
            "include_private_images": include_images,
            "status": "requested",
        }
        self._run_package_requests.append(package_request)
        self.diagnostics.event(
            "complete_run_bundle_export_requested",
            action="Finish test and save complete ZIP",
            request="Generate canonical scan artifacts and validated archive",
            state="preparing",
            result="started",
            test_run_id=run_id,
            destination_name=destination.name,
            include_private_images=include_images,
        )
        progress = QProgressDialog(
            "Preparing complete test package…", "Cancel", 0, 8, self
        )
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setValue(0)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)

        def package_progress(phase: str, completed: int, total: int) -> None:
            if total > 0:
                detail = f"{completed / (1024 * 1024):.1f} of {total / (1024 * 1024):.1f} MiB"
            else:
                detail = "working"
            progress.setLabelText(f"{phase}…\n{detail}")
            QApplication.processEvents()

        try:
            if self.mesh is None:
                try:
                    self.diagnostics.event(
                        "complete_run_mesh_creation_requested",
                        state="processing",
                        result="started",
                        source_point_count=len(self.cleaned_cloud.points),
                    )
                    self.mesh = build_front_surface(self.cleaned_cloud)
                    self.review_page.set_model(self.cleaned_cloud, self.mesh)
                    self.diagnostics.event(
                        "complete_run_mesh_created",
                        state="review",
                        result="ok",
                        triangle_count=len(self.mesh.faces),
                    )
                except Exception as error:
                    self.mesh = None
                    self.diagnostics.event(
                        "complete_run_mesh_creation_failed", failure=error
                    )
            progress.setValue(1)
            QApplication.processEvents()

            artifacts: list[RunBundleArtifact] = []
            generation_failures: list[dict[str, str]] = []

            destination.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(
                prefix="laserline3d-complete-run-", dir=destination.parent
            ) as temporary:
                staging = Path(temporary)

                def stage_file(
                    archive_path: str,
                    *,
                    role: str,
                    stage: str,
                    writer: object,
                    relationship: ArtifactRelationship | None = None,
                    required: bool = True,
                    image_opt_in: bool = False,
                ) -> Path | None:
                    output = staging.joinpath(*archive_path.split("/"))
                    output.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        writer(output)  # type: ignore[operator]
                        if not output.is_file():
                            raise RuntimeError("artifact writer produced no file")
                        artifacts.append(
                            RunBundleArtifact(
                                archive_path,
                                output,
                                role,
                                stage,
                                relationship=relationship,
                                required=required,
                                requires_image_opt_in=image_opt_in,
                            )
                        )
                        return output
                    except Exception as error:
                        reason = f"{type(error).__name__}: {error}"
                        generation_failures.append(
                            {"archive_path": archive_path, "failure": reason}
                        )
                        artifacts.append(
                            RunBundleArtifact(
                                archive_path,
                                None,
                                role,
                                stage,
                                relationship=relationship,
                                required=required,
                                requires_image_opt_in=image_opt_in,
                                missing_reason=reason,
                            )
                        )
                        self.diagnostics.event(
                            "complete_run_artifact_generation_failed",
                            failure=error,
                            archive_path=archive_path,
                            role=role,
                            stage=stage,
                        )
                        return None

                final_cloud = self.cleaned_cloud
                raw_cloud: PointCloud | None = None
                raw_spool = self._raw_fused_spool_path
                if (
                    self._cloud_cleanup_applied
                    and raw_spool is not None
                    and raw_spool.is_file()
                ):
                    raw_point_count = self._raw_fused_point_count
                    artifacts.append(
                        RunBundleArtifact(
                            "models/raw/fused-scan.ply",
                            raw_spool,
                            "point_cloud",
                            "raw_fused",
                        )
                    )
                else:
                    if self._cloud_cleanup_applied and self.accumulator.accepted_frames:
                        self.diagnostics.event(
                            "raw_fused_cloud_rebuilt_for_bundle",
                            state="fallback",
                            result="started",
                            reason="pre_cleanup_spool_unavailable",
                        )
                        raw_cloud = self.accumulator.cloud()
                    else:
                        raw_cloud = final_cloud
                    raw_point_count = len(raw_cloud.points)
                    self._raw_fused_point_count = raw_point_count
                    stage_file(
                        "models/raw/fused-scan.ply",
                        role="point_cloud",
                        stage="raw_fused",
                        writer=lambda path: export_point_cloud_ply(path, raw_cloud),
                    )
                raw_metadata = self._export_metadata(
                    "point_cloud",
                    cloud=raw_cloud if raw_cloud is not None else final_cloud,
                    mesh=None,
                    stage="raw_fused",
                )
                raw_metadata["point_count"] = raw_point_count
                stage_file(
                    "models/raw/fused-scan.ply.json",
                    role="metadata_sidecar",
                    stage="raw_fused",
                    relationship=ArtifactRelationship(
                        "sidecar_for", "models/raw/fused-scan.ply"
                    ),
                    writer=lambda path: write_export_metadata(path, raw_metadata),
                )
                progress.setValue(2)
                QApplication.processEvents()

                stage_file(
                    "models/final/scan.ply",
                    role="point_cloud",
                    stage="final_reviewed",
                    writer=lambda path: export_point_cloud_ply(path, final_cloud),
                )
                stage_file(
                    "models/final/scan.ply.json",
                    role="metadata_sidecar",
                    stage="final_reviewed",
                    relationship=ArtifactRelationship(
                        "sidecar_for", "models/final/scan.ply"
                    ),
                    writer=lambda path: write_export_metadata(
                        path,
                        self._export_metadata(
                            "point_cloud", cloud=final_cloud, stage="final_reviewed"
                        ),
                    ),
                )
                progress.setValue(3)
                QApplication.processEvents()

                if self.mesh is not None:
                    obj_writer = lambda path: export_obj(path, self.mesh)  # noqa: E731
                    stl_writer = lambda path: export_binary_stl(path, self.mesh)  # noqa: E731
                else:
                    def obj_writer(_path: Path) -> None:
                        raise RuntimeError("surface mesh could not be created")

                    def stl_writer(_path: Path) -> None:
                        raise RuntimeError("surface mesh could not be created")

                stage_file(
                    "models/final/scan.obj",
                    role="surface_mesh",
                    stage="final_reviewed",
                    writer=obj_writer,
                )
                stage_file(
                    "models/final/scan.obj.json",
                    role="metadata_sidecar",
                    stage="final_reviewed",
                    relationship=ArtifactRelationship(
                        "sidecar_for", "models/final/scan.obj"
                    ),
                    writer=lambda path: write_export_metadata(
                        path, self._export_metadata("surface_mesh", stage="final_reviewed")
                    ),
                )
                stage_file(
                    "models/final/scan.stl",
                    role="surface_mesh",
                    stage="final_reviewed",
                    writer=stl_writer,
                )
                stage_file(
                    "models/final/scan.stl.json",
                    role="metadata_sidecar",
                    stage="final_reviewed",
                    relationship=ArtifactRelationship(
                        "sidecar_for", "models/final/scan.stl"
                    ),
                    writer=lambda path: write_export_metadata(
                        path, self._export_metadata("surface_mesh", stage="final_reviewed")
                    ),
                )
                progress.setValue(4)
                QApplication.processEvents()

                if self.camera_calibration is not None:
                    stage_file(
                        "calibration/camera.json",
                        role="camera_calibration",
                        stage="calibration",
                        writer=lambda path: save_camera_calibration(
                            path, self.camera_calibration
                        ),
                    )
                else:
                    artifacts.append(
                        RunBundleArtifact(
                            "calibration/camera.json",
                            None,
                            "camera_calibration",
                            "calibration",
                            missing_reason="camera calibration unavailable",
                        )
                    )
                if self.corner_calibration is not None:
                    stage_file(
                        "calibration/corner.json",
                        role="corner_calibration",
                        stage="calibration",
                        writer=lambda path: save_corner_calibration(
                            path, self.corner_calibration
                        ),
                    )
                else:
                    artifacts.append(
                        RunBundleArtifact(
                            "calibration/corner.json",
                            None,
                            "corner_calibration",
                            "calibration",
                            missing_reason="corner calibration unavailable",
                        )
                    )
                if self.camera_calibration is not None and self.corner_calibration is not None:
                    stage_file(
                        "project/scan.llscan",
                        role="editable_project",
                        stage="final_reviewed",
                        writer=lambda path: save_project(
                            path,
                            final_cloud,
                            self.camera_calibration,
                            self.corner_calibration,
                            name="complete-test-run",
                            metadata=self._test_run_summary(),
                        ),
                    )
                else:
                    artifacts.append(
                        RunBundleArtifact(
                            "project/scan.llscan",
                            None,
                            "editable_project",
                            "final_reviewed",
                            missing_reason="calibration required for project file",
                        )
                    )
                progress.setValue(5)
                QApplication.processEvents()

                for index, (model_path, metadata_path, kind) in enumerate(
                    self._run_exported_artifacts, start=1
                ):
                    base = f"manual-exports/{index:03d}-{model_path.name}"
                    artifacts.append(
                        RunBundleArtifact(
                            base,
                            model_path,
                            kind,
                            "manual_export",
                            required=False,
                            missing_reason="manual export no longer exists",
                        )
                    )
                    artifacts.append(
                        RunBundleArtifact(
                            f"{base}.json",
                            metadata_path,
                            "metadata_sidecar",
                            "manual_export",
                            relationship=ArtifactRelationship("sidecar_for", base),
                            required=False,
                            missing_reason="manual export sidecar no longer exists",
                        )
                    )

                def write_image(path: Path, image: np.ndarray | None) -> None:
                    if image is None or not cv2.imwrite(str(path), image):
                        raise RuntimeError("camera image unavailable or could not be encoded")

                if include_images:
                    stage_file(
                        "images/current-camera-frame.jpg",
                        role="camera_image",
                        stage="run_end",
                        writer=lambda path: write_image(path, self._test_run_end_frame),
                        required=False,
                        image_opt_in=True,
                    )
                    stage_file(
                        "images/laser-off-background.png",
                        role="background_image",
                        stage="laser_tuning",
                        writer=lambda path: write_image(path, self.background),
                        required=False,
                        image_opt_in=True,
                    )
                else:
                    for archive_path, role, stage_name in (
                        ("images/current-camera-frame.jpg", "camera_image", "run_end"),
                        ("images/laser-off-background.png", "background_image", "laser_tuning"),
                    ):
                        artifacts.append(
                            RunBundleArtifact(
                                archive_path,
                                None,
                                role,
                                stage_name,
                                required=False,
                                requires_image_opt_in=True,
                                missing_reason="user did not opt in",
                            )
                        )
                progress.setValue(6)
                QApplication.processEvents()

                run_summary = self._test_run_summary()
                run_summary["artifact_generation_failures"] = generation_failures
                package_status = (
                    "partial"
                    if any(
                        item.required
                        and item.source_path is None
                        and not item.requires_image_opt_in
                        for item in artifacts
                    )
                    else "completed"
                )
                if not self._test_run_finalized:
                    self.diagnostics.event(
                        "complete_run_bundle_artifacts_prepared",
                        state="ready_to_package",
                        result=package_status,
                        artifact_count=len(artifacts),
                        generation_failure_count=len(generation_failures),
                    )
                    self.diagnostics.finish_test_run(
                        status=package_status, summary=run_summary
                    )
                    self._test_run_finalized = True
                run_metadata = self.diagnostics.test_run_metadata(run_id)
                run_summary = {**run_metadata, **run_summary}
                settings = (
                    self._test_run_frozen_settings
                    if self._test_run_frozen_settings is not None
                    else self._run_settings_snapshot()
                )
                bundle = create_complete_run_bundle(
                    destination,
                    application_session_id=self.diagnostics.session_id,
                    test_run_id=run_id,
                    application_version=__version__,
                    diagnostics_jsonl=self.diagnostics.test_run_snapshot(run_id),
                    artifacts=artifacts,
                    scan_operation_id=self._scan_operation_id,
                    run_summary=run_summary,
                    settings=settings,
                    run_started_utc=run_metadata.get("started_utc"),
                    run_finished_utc=run_metadata.get("finished_utc"),
                    run_status=str(run_metadata.get("status", package_status)),
                    include_private_images=include_images,
                    progress_callback=package_progress,
                    cancel_check=progress.wasCanceled,
                )
                progress.setValue(8)
            package_request["status"] = "published"
            self._test_run_saved = package_status == "completed"
            self.diagnostics.event(
                "complete_run_bundle_exported",
                action="Finish test and save complete ZIP",
                state="saved",
                result="ok" if self._test_run_saved else "partial",
                test_run_id=run_id,
                destination_name=bundle.name,
                included_private_images=include_images,
            )
            if self._test_run_saved:
                self._update_test_run_status(
                    "complete ZIP saved; start a new run for the next test"
                )
                QMessageBox.information(
                    self,
                    "Complete test saved",
                    f"Saved one complete test package:\n{bundle}\n\n"
                    "It contains the run diagnostics, project, PLY, OBJ, STL, JSON sidecars, settings, and integrity hashes. "
                    "Start a new test run before changing the test setup.",
                )
            else:
                self._update_test_run_status(
                    "partial ZIP saved; missing artifacts are recorded and save can be retried"
                )
                QMessageBox.warning(
                    self,
                    "Partial test package saved",
                    f"Saved a partial test package:\n{bundle}\n\n"
                    "One or more required artifacts could not be created. The manifest records exactly what is missing. "
                    "You can retry this save or start a new run after reviewing the package.",
                )
        except RunBundleCancelledError:
            package_request["status"] = "cancelled"
            self._update_test_run_status("ZIP save cancelled; you can retry")
            self.diagnostics.event(
                "complete_run_bundle_export_cancelled",
                result="cancelled",
                test_run_id=run_id,
                destination_name=destination.name,
            )
        except Exception as error:
            package_request["status"] = "failed"
            package_request["failure_type"] = type(error).__name__
            self._update_test_run_status("ZIP save failed; you can retry")
            self.diagnostics.event(
                "complete_run_bundle_export_failed",
                failure=error,
                test_run_id=run_id,
                destination_name=destination.name,
            )
            self._error("Could not save complete test ZIP", str(error))
        finally:
            QApplication.restoreOverrideCursor()
            progress.close()

    def run_synthetic_demo(self) -> None:
        progress = QProgressDialog("Running verified virtual camera scan…", "Cancel", 0, 28, self)
        progress.setWindowModality(Qt.WindowModal)
        rig = make_synthetic_rig()
        self.camera_calibration = rig.camera
        self.corner_calibration = rig.corner
        self.rig_page.roi = rig.corner.object_roi
        self.background = rig.background_bgr
        laser = LaserSettings(
            minimum_red=110,
            minimum_dominance=40,
            threshold=35.0,
            minimum_component_px=5,
            orientation="horizontal",
            use_background=True,
        )
        settings = ScanSettings(
            min_reference_points_per_wall=8,
            ransac_distance_mm=1.8,
            max_plane_rms_mm=2.2,
            voxel_size_mm=1.0,
        )
        self.reconstructor = FrameReconstructor(rig.camera, rig.corner, laser, settings)
        accumulator = ScanAccumulator(settings.voxel_size_mm)
        try:
            for index, level in enumerate(np.linspace(45.0, 355.0, 28)):
                if progress.wasCanceled():
                    return
                frame = render_laser_frame(rig, float(level), seed=index)
                result = self.reconstructor.process(
                    frame,
                    frame_index=index,
                    timestamp_s=index / 15.0,
                    background_bgr=rig.background_bgr,
                )
                accumulator.add(result)
                progress.setValue(index + 1)
                QApplication.processEvents()
            if accumulator.accepted_frames < 10:
                raise RuntimeError(
                    f"Synthetic validation accepted only {accumulator.accepted_frames} frames"
                )
            self._discard_raw_fused_spool()
            self._cloud_cleanup_applied = False
            self._active_scan_settings = settings
            self.accumulator = accumulator
            self.cleaned_cloud = accumulator.cloud()
            self._raw_fused_point_count = len(self.cleaned_cloud.points)
            self.mesh = build_front_surface(
                self.cleaned_cloud, max_image_edge_px=45.0, max_world_edge_mm=24.0
            )
            self.review_page.set_model(self.cleaned_cloud, self.mesh)
            self.navigation.setCurrentRow(6)
            self.diagnostics.event(
                "synthetic_demo_completed",
                test_result="passed",
                accepted_frames=accumulator.accepted_frames,
                points=len(self.cleaned_cloud.points),
                triangles=len(self.mesh.faces),
            )
        except Exception as error:
            self._error("Synthetic verification failed", str(error))
            self.diagnostics.event("synthetic_demo_failed", failure=error, test_result="failed")
        finally:
            progress.close()

    @staticmethod
    def app_data_directory() -> Path:
        root = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
        path = Path(root)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def open_checkerboard_pdf(self) -> None:
        self._open_printable(CHECKERBOARD_PDF, "checkerboard")

    def open_setup_guide_pdf(self) -> None:
        self._open_printable(SETUP_GUIDE_PDF, "setup guide")

    def _open_printable(self, filename: str, label: str) -> None:
        path = printable_path(filename)
        if not path.is_file():
            self._error(
                "Printable file missing",
                f"The {label} PDF was not found. Reinstall or rebuild the complete application folder.",
            )
            self.diagnostics.event("printable_open_failed", failure="missing", path=str(path))
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            self._error("Could not open printable", f"Open this file manually:\n{path}")
            self.diagnostics.event("printable_open_failed", failure="open_url", path=str(path))
            return
        self.diagnostics.event("printable_opened", result="ok", kind=label, path=str(path))

    def _error(self, title: str, message: str) -> None:
        QMessageBox.warning(self, title, message)

    def closeEvent(self, event: object) -> None:
        if self.isVisible() and self._has_unsaved_test_evidence():
            answer = QMessageBox.question(
                self,
                "Close without saving the test?",
                "This test has evidence that has not been saved as a complete ZIP.\n\n"
                "Close the application and leave this test unsaved?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                self.diagnostics.event(
                    "application_close_cancelled",
                    result="cancelled",
                    reason="unsaved_test_evidence",
                )
                event.ignore()  # type: ignore[attr-defined]
                return
        self.scanning = False
        self._camera_snapshot_timer.stop()
        application = QApplication.instance()
        if application is not None:
            application.removeEventFilter(self)
        if self.processing_worker is not None and self.processing_worker.isRunning():
            self.processing_worker.request_stop()
            self.processing_worker.wait(3000)
        if self.camera_worker is not None and self.camera_worker.isRunning():
            self.camera_worker.request_stop()
            self.camera_worker.wait(3000)
        self._discard_raw_fused_spool()
        self.diagnostics.event("application_closed", result="ok")
        event.accept()  # type: ignore[attr-defined]


def _size(width: int, height: int):
    from PySide6.QtCore import QSize

    return QSize(width, height)


def _safe_key_category(key: int) -> str:
    """Describe a key's function without retaining printable key identity."""

    named = {
        int(Qt.Key.Key_Escape): "escape",
        int(Qt.Key.Key_Return): "activate",
        int(Qt.Key.Key_Enter): "activate",
        int(Qt.Key.Key_Space): "activate",
        int(Qt.Key.Key_Tab): "focus_next",
        int(Qt.Key.Key_Backtab): "focus_previous",
        int(Qt.Key.Key_Left): "navigate_left",
        int(Qt.Key.Key_Right): "navigate_right",
        int(Qt.Key.Key_Up): "navigate_up",
        int(Qt.Key.Key_Down): "navigate_down",
        int(Qt.Key.Key_Home): "navigate_home",
        int(Qt.Key.Key_End): "navigate_end",
        int(Qt.Key.Key_PageUp): "navigate_page_up",
        int(Qt.Key.Key_PageDown): "navigate_page_down",
        int(Qt.Key.Key_Backspace): "edit_backspace",
        int(Qt.Key.Key_Delete): "edit_delete",
        int(Qt.Key.Key_Insert): "edit_insert",
        int(Qt.Key.Key_Plus): "increase",
        int(Qt.Key.Key_Minus): "decrease",
    }
    if key in named:
        return named[key]
    if int(Qt.Key.Key_F1) <= key <= int(Qt.Key.Key_F35):
        return "function_key"
    if (
        int(Qt.Key.Key_0) <= key <= int(Qt.Key.Key_9)
        or int(Qt.Key.Key_A) <= key <= int(Qt.Key.Key_Z)
    ):
        return "printable_or_shortcut_key"
    return "other_key"


def _safe_modifiers(modifiers: object) -> list[str]:
    result: list[str] = []
    for flag, name in (
        (Qt.KeyboardModifier.ControlModifier, "control"),
        (Qt.KeyboardModifier.AltModifier, "alt"),
        (Qt.KeyboardModifier.ShiftModifier, "shift"),
        (Qt.KeyboardModifier.MetaModifier, "meta"),
    ):
        try:
            if modifiers & flag:  # type: ignore[operator]
                result.append(name)
        except TypeError:
            break
    return result


def _safe_mouse_button(button: object) -> str:
    return {
        Qt.MouseButton.LeftButton: "left",
        Qt.MouseButton.RightButton: "right",
        Qt.MouseButton.MiddleButton: "middle",
    }.get(button, "other")
