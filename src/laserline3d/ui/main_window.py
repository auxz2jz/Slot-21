from __future__ import annotations

import json
import tempfile
import time
import uuid
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
from PySide6.QtCore import QStandardPaths, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QStackedWidget,
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
from ..camera import CameraRequest, CameraWorker
from ..diagnostics import DiagnosticLog
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
from ..synthetic import make_synthetic_rig, render_laser_frame
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
        self._background_sum: np.ndarray | None = None
        self._background_remaining = 0
        self.reconstructor: FrameReconstructor | None = None
        self.accumulator = ScanAccumulator()
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
        self._laser_log_timer = QTimer(self)
        self._laser_log_timer.setSingleShot(True)
        self._laser_log_timer.setInterval(300)
        self._laser_log_timer.timeout.connect(self._log_laser_settings)

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
        self.navigation.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.navigation.currentRowChanged.connect(self._page_changed)
        self.navigation.setCurrentRow(0)
        self._connect_page_actions()

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
        self.review_page.clean_requested.connect(self.clean_cloud)
        self.review_page.mesh_requested.connect(self.create_mesh)
        self.review_page.save_project_requested.connect(self.save_project_dialog)
        self.review_page.export_ply_requested.connect(self.export_ply_dialog)
        self.review_page.export_obj_requested.connect(self.export_obj_dialog)
        self.review_page.export_stl_requested.connect(self.export_stl_dialog)

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

    def _invalidate_laser_background(self, reason: str) -> bool:
        invalidated = bool(
            self.background is not None
            or self._background_sum is not None
            or self._background_remaining > 0
        )
        self.background = None
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
        self.diagnostics.event(
            "camera_driver_settings_requested",
            action="Camera driver settings",
            request="Open native camera controls",
        )

    def refresh_camera_properties(self) -> None:
        if self.camera_worker is None:
            self._error("Camera not connected", "Connect the camera first.")
            return
        self.camera_worker.request_property_snapshot()
        self.diagnostics.event(
            "camera_property_snapshot_requested",
            action="Refresh reported values",
            request="Read raw camera properties",
        )

    def on_camera_properties_reported(self, properties: object) -> None:
        if not self._current_camera_signal():
            return
        reported = dict(properties)  # type: ignore[arg-type]
        previous: dict[str, object] = {}
        if self.camera_details is not None:
            old = self.camera_details.get("properties")
            if isinstance(old, dict):
                previous = dict(old)
            self.camera_details["properties"] = reported
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
        if changed:
            background_invalidated = self._invalidate_laser_background(
                "Camera controls changed—capture a new laser-off background"
            )
            geometric_controls = {"Autofocus", "Focus", "Zoom"}
            calibration_invalidated = bool(geometric_controls.intersection(changed)) and (
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
        self.camera_page.set_reported_properties(reported)
        self.diagnostics.event(
            "camera_properties_reported",
            state="camera_ready",
            result="ok",
            properties=reported,
            changed=changed,
            background_invalidated=background_invalidated,
            calibration_invalidated=calibration_invalidated,
            note="Raw values; zero may also mean unsupported",
        )

    def on_camera_frame(self, frame: object, timestamp: float, sequence: int) -> None:
        if not self._current_camera_signal():
            return
        image = np.asarray(frame, dtype=np.uint8)
        self.latest_frame = image
        self.latest_timestamp = timestamp
        self.latest_sequence = sequence
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
                self._background_sum = None
                self.tune_page.background_status.setText("Background captured—turn the laser on")
                self.diagnostics.event(
                    "background_captured",
                    action="Capture 15 laser-off frames",
                    state="ready_for_laser",
                    result="ok",
                    frames=15,
                    resolution=[int(self.background.shape[1]), int(self.background.shape[0])],
                    channel_means_bgr=np.mean(self.background, axis=(0, 1)).round(2).tolist(),
                    channel_min_bgr=np.min(self.background, axis=(0, 1)).tolist(),
                    channel_max_bgr=np.max(self.background, axis=(0, 1)).tolist(),
                )
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
        )

    def reset_calibration_views(self) -> None:
        self.calibrator = None
        self.lens_page.count.set_status("0 accepted; 12 minimum", "neutral")
        self.lens_page.message.setText("Captured calibration views were cleared.")

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
        self.diagnostics.event("object_roi_frame", action="Capture object view", result="ok")

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
        return ScanSettings()

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
            background_drift = None
            if self.background is not None and self.background.shape == frame.shape:
                background_drift = float(
                    np.median(
                        np.abs(frame.astype(np.int16) - self.background.astype(np.int16))
                    )
                )
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
                f"{result.detection.saturated_fraction * 100:.1f}% saturated",
                level,
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
                    detected_points=result.quality.detected_points,
                    object_points=result.quality.object_points,
                    left_reference_points=result.quality.left_reference_points,
                    right_reference_points=result.quality.right_reference_points,
                    saturated_fraction=result.quality.saturated_fraction,
                    plane_rms_mm=result.quality.plane_rms_mm,
                    median_background_change=background_drift,
                    background_mismatch=background_warning,
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
        self._finish_pending = False
        self._last_submit_time = 0.0
        if self._scan_operation_id is None or not self.accumulator.accepted_frames:
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

    def finish_scan(self) -> None:
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
            )
            self._error("No scan data", "No frames passed the reference and geometry checks.")
            return
        self.cleaned_cloud = cloud
        self.mesh = None
        self.review_page.set_model(cloud, None)
        self.scan_page.set_scan_state("paused", has_data=True)
        self.navigation.setCurrentRow(6)
        self.diagnostics.event(
            "scan_finished",
            state="review",
            result="ok",
            operation_id=self._scan_operation_id,
            accepted_frames=self.accumulator.accepted_frames,
            rejected_frames=self.accumulator.rejected_frames,
            point_count=len(cloud.points),
            rejection_reasons=dict(self._scan_rejection_counts),
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
        self.accumulator = ScanAccumulator()
        self.cleaned_cloud = None
        self.mesh = None
        self._processed_frame_count = 0
        previous_reasons = dict(self._scan_rejection_counts)
        self._scan_rejection_counts.clear()
        self._scan_operation_id = None
        self.scan_page.cloud.set_cloud(None)
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
        if accepted and self.accumulator.accepted_frames % 5 == 0:
            self.scan_page.cloud.set_cloud(self.accumulator.cloud())
        quality = processed.quality
        if not accepted:
            self._scan_rejection_counts[quality.message] += 1
        self.diagnostics.event(
            "scan_frame_processed",
            state="accepted" if accepted else "rejected",
            result="ok",
            operation_id=self._scan_operation_id,
            processed_frame=self._processed_frame_count,
            accepted=accepted,
            reason=quality.message,
            detected_points=quality.detected_points,
            object_points=quality.object_points,
            left_reference_points=quality.left_reference_points,
            right_reference_points=quality.right_reference_points,
            plane_rms_mm=quality.plane_rms_mm,
            support_ratio=quality.support_ratio,
            median_triangulation_angle_deg=quality.median_triangulation_angle_deg,
            saturated_fraction=quality.saturated_fraction,
            accumulated_accepted=self.accumulator.accepted_frames,
            accumulated_rejected=self.accumulator.rejected_frames,
            worker_dropped_frames=dropped,
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
            },
            "laser_off_background": background_summary,
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
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            cleaned = remove_statistical_outliers(source)
            removed = len(source.points) - len(cleaned.points)
            self.cleaned_cloud = cleaned
            self.mesh = None
            self.review_page.set_model(cleaned, None)
            self.review_page.summary.set_status(
                f"{len(cleaned.points):,} points • removed {removed:,} isolated points • no surface yet",
                "good",
            )
        except Exception as error:
            self._error("Cleanup failed", str(error))
        finally:
            QApplication.restoreOverrideCursor()

    def create_mesh(self) -> None:
        cloud = self.cleaned_cloud or self.accumulator.cloud()
        if not len(cloud.points):
            self._error("No points", "Finish a scan or open a project first.")
            return
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
            self.diagnostics.event("project_saved", result="ok", path=str(path))
        except Exception as error:
            self._error("Could not save project", str(error))

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
            self.review_page.set_model(cloud, None)
            self.navigation.setCurrentRow(6)
            self.diagnostics.event("project_opened", result="ok", path=path_text)
        except Exception as error:
            self._error("Could not open project", str(error))

    def _export_metadata(self, kind: str) -> dict[str, object]:
        return {
            "artifact": kind,
            "application_version": __version__,
            "point_count": len(self.cleaned_cloud.points) if self.cleaned_cloud else 0,
            "triangle_count": len(self.mesh.faces) if self.mesh else 0,
            "mesh_is_watertight": is_watertight(self.mesh) if self.mesh else False,
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

    def _run_export(self, path: Path, exporter: object, payload: object, kind: str) -> None:
        try:
            exporter(path, payload)  # type: ignore[operator]
            write_export_metadata(path.with_suffix(path.suffix + ".json"), self._export_metadata(kind))
            self.diagnostics.event("model_exported", result="ok", path=str(path), format=path.suffix)
            QMessageBox.information(self, "Export complete", f"Saved:\n{path}")
        except Exception as error:
            self._error("Export failed", str(error))

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
            self.accumulator = accumulator
            self.cleaned_cloud = accumulator.cloud()
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
        self.scanning = False
        if self.processing_worker is not None and self.processing_worker.isRunning():
            self.processing_worker.request_stop()
            self.processing_worker.wait(3000)
        if self.camera_worker is not None and self.camera_worker.isRunning():
            self.camera_worker.request_stop()
            self.camera_worker.wait(3000)
        self.diagnostics.event("application_closed", result="ok")
        event.accept()  # type: ignore[attr-defined]


def _size(width: int, height: int):
    from PySide6.QtCore import QSize

    return QSize(width, height)
