from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..camera import BACKENDS, CameraRequest
from ..models import LaserSettings, Mesh, PointCloud
from ..reconstruction import FrameQuality
from .widgets import CornerLandmarkDiagram, PointCloudView, StatusCard, VideoCanvas


class WizardPage(QWidget):
    def __init__(self, title: str, description: str) -> None:
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(28, 24, 28, 24)
        self.layout.setSpacing(14)
        heading = QLabel(title)
        heading.setObjectName("pageTitle")
        subtitle = QLabel(description)
        subtitle.setObjectName("pageDescription")
        subtitle.setWordWrap(True)
        subtitle.setMaximumWidth(1000)
        self.layout.addWidget(heading)
        self.layout.addWidget(subtitle)


class WelcomePage(WizardPage):
    connect_camera = Signal()
    synthetic_demo = Signal()
    open_project = Signal()

    def __init__(self) -> None:
        super().__init__(
            "LaserLine 3D Scanner",
            "Create a measured 3D surface by sweeping a red laser line across an object. "
            "The fixed camera reads the object stripe while two reference wings locate the handheld laser in every frame.",
        )
        warning = QFrame()
        warning.setObjectName("notice")
        warning_layout = QVBoxLayout(warning)
        warning_layout.addWidget(QLabel("Before you scan"))
        details = QLabel(
            "You will calibrate two different things: first the camera lens with the supplied printed checkerboard, "
            "then the scan space with two plain rigid matte-white panels joined as a vertical V. During scanning, "
            "keep both reference wings, the object, and the same laser stripe visible. The first release captures "
            "the camera-visible surface; it does not invent hidden backs."
        )
        details.setWordWrap(True)
        warning_layout.addWidget(details)
        self.layout.addWidget(warning)
        safety = QLabel(
            "Laser safety: use a low-power line laser, wear protection appropriate to its wavelength/class, "
            "and never aim it at eyes or reflective surfaces."
        )
        safety.setObjectName("safetyText")
        safety.setWordWrap(True)
        self.layout.addWidget(safety)
        buttons = QHBoxLayout()
        new_scan = QPushButton("Connect camera and start")
        new_scan.setObjectName("primaryButton")
        new_scan.clicked.connect(self.connect_camera)
        sample = QPushButton("Run built-in synthetic self-test")
        sample.clicked.connect(self.synthetic_demo)
        open_button = QPushButton("Open .llscan project")
        open_button.clicked.connect(self.open_project)
        buttons.addWidget(new_scan)
        buttons.addWidget(sample)
        buttons.addWidget(open_button)
        buttons.addStretch()
        self.layout.addLayout(buttons)
        self.layout.addStretch()


class CameraPage(WizardPage):
    connect_requested = Signal(object)
    disconnect_requested = Signal()
    native_settings_requested = Signal()
    refresh_properties_requested = Signal()

    def __init__(self) -> None:
        super().__init__(
            "1. Connect the camera",
            "Mount the Logitech camera rigidly, frame both reference wings, and choose the highest stable resolution. "
            "Do not change focus, zoom, or resolution after lens calibration.",
        )
        camera_help = QLabel(
            "Before lens calibration, open the camera driver settings. If available, turn off autofocus, auto exposure, "
            "and automatic white balance; focus once, keep gain low, and shorten exposure until the laser is a narrow "
            "red stripe rather than a glowing band. Avoid high sharpness because it can add false edges. Keep every "
            "setting unchanged through corner calibration, background capture, and scanning."
        )
        camera_help.setObjectName("safetyText")
        camera_help.setWordWrap(True)
        camera_help.setMaximumWidth(1000)
        self.layout.addWidget(camera_help)
        controls = QFrame()
        controls.setObjectName("panel")
        form = QFormLayout(controls)
        self.camera_index = QSpinBox()
        self.camera_index.setRange(0, 15)
        self.backend = QComboBox()
        self.backend.addItems(BACKENDS.keys())
        self.resolution = QComboBox()
        for label, size in [
            ("640 × 480", (640, 480)),
            ("1280 × 720", (1280, 720)),
            ("1920 × 1080", (1920, 1080)),
        ]:
            self.resolution.addItem(label, size)
        self.resolution.setCurrentIndex(1)
        self.fps = QSpinBox()
        self.fps.setRange(5, 60)
        self.fps.setValue(30)
        form.addRow("Camera number", self.camera_index)
        form.addRow("Windows backend", self.backend)
        form.addRow("Resolution", self.resolution)
        form.addRow("Requested frame rate", self.fps)
        row = QHBoxLayout()
        self.connect_button = QPushButton("Connect")
        self.connect_button.setObjectName("primaryButton")
        self.connect_button.clicked.connect(self._connect)
        self.disconnect_button = QPushButton("Disconnect")
        self.disconnect_button.setEnabled(False)
        self.disconnect_button.clicked.connect(self.disconnect_requested)
        self.settings_button = QPushButton("Camera driver settings…")
        self.settings_button.setEnabled(False)
        self.settings_button.setToolTip(
            "Opens the manufacturer's Windows controls; available with the DirectShow backend when the driver supports it."
        )
        self.settings_button.clicked.connect(self.native_settings_requested)
        self.refresh_properties = QPushButton("Refresh reported values")
        self.refresh_properties.setEnabled(False)
        self.refresh_properties.clicked.connect(self.refresh_properties_requested)
        row.addWidget(self.connect_button)
        row.addWidget(self.disconnect_button)
        row.addStretch()
        form.addRow(row)
        settings_row = QHBoxLayout()
        settings_row.addWidget(self.settings_button)
        settings_row.addWidget(self.refresh_properties)
        settings_row.addStretch()
        form.addRow(settings_row)
        controls.setMaximumWidth(600)
        self.status = StatusCard("Camera status")
        self.properties = StatusCard(
            "Raw controls reported by driver",
            "Connect first. A value of 0 can mean either zero/off or unsupported.",
        )
        self.status.setMaximumWidth(460)
        self.properties.setMaximumWidth(460)
        top = QHBoxLayout()
        top.addWidget(controls, 2)
        reports = QVBoxLayout()
        reports.addWidget(self.status)
        reports.addWidget(self.properties)
        top.addLayout(reports, 3)
        self.layout.addLayout(top)
        model_note = QLabel(
            "Camera model names and control ranges are not reliably exposed through OpenCV. Use the model printed on "
            "the camera or shown in Windows for model-specific help. Most webcams have no optical zoom; driver zoom is "
            "usually a digital crop and any focus/zoom/crop change requires both calibrations again."
        )
        model_note.setWordWrap(True)
        model_note.setMaximumWidth(1000)
        self.layout.addWidget(model_note)
        self.canvas = VideoCanvas("Connect a camera to see its image")
        self.layout.addWidget(self.canvas, 1)

    def _connect(self) -> None:
        width, height = self.resolution.currentData()
        request = CameraRequest(
            index=self.camera_index.value(),
            backend=BACKENDS[self.backend.currentText()],
            width=width,
            height=height,
            fps=float(self.fps.value()),
        )
        self.connect_requested.emit(request)

    def set_connected(self, details: dict[str, object]) -> None:
        self.connect_button.setEnabled(False)
        self.disconnect_button.setEnabled(True)
        self.settings_button.setEnabled(True)
        self.refresh_properties.setEnabled(True)
        self.status.set_status(
            f"Connected through {details['backend']} at {details['width']} × {details['height']} "
            f"({details['fps']:.1f} fps reported)",
            "good",
        )
        reported = details.get("properties")
        if isinstance(reported, dict):
            self.set_reported_properties(reported)

    def set_reported_properties(self, properties: dict[str, object]) -> None:
        order = (
            "Autofocus",
            "Focus",
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
            "Sensor temperature",
            "Iris",
            "Zoom",
            "Video FourCC",
            "Capture buffer size",
        )
        values = []
        for name in order:
            if name not in properties:
                continue
            try:
                value = f"{float(properties[name]):g}"
            except (TypeError, ValueError):
                value = str(properties[name])
            values.append(f"{name}: {value}")
        self.properties.set_status(
            "  •  ".join(values)
            + "\nRaw values only: availability and ranges depend on the camera, driver, and Windows backend.",
            "neutral",
        )

    def set_disconnected(self, message: str = "Not connected") -> None:
        self.connect_button.setEnabled(True)
        self.disconnect_button.setEnabled(False)
        self.settings_button.setEnabled(False)
        self.refresh_properties.setEnabled(False)
        self.status.set_status(message, "bad" if "error" in message.lower() else "neutral")
        self.properties.set_status(
            "Connect first. A value of 0 can mean either zero/off or unsupported.", "neutral"
        )


class LensCalibrationPage(WizardPage):
    capture_requested = Signal()
    reset_requested = Signal()
    calculate_requested = Signal()
    load_requested = Signal()
    open_checkerboard_requested = Signal()
    open_guide_requested = Signal()

    def __init__(self) -> None:
        super().__init__(
            "2. Calibrate the camera lens",
            "This step measures lens distortion; it does not calibrate the white V fixture. Print the supplied "
            "10 x 7 square board (9 x 6 inside crossings), mount it flat, and hold it in the air where the object will be.",
        )
        preparation = QLabel(
            "Print at Actual size / 100%, measure a square, and turn the laser off. Capture the center, all four "
            "image corners, near and far distances, and several tilts. Do not leave the board flat on the base for every photo."
        )
        preparation.setObjectName("safetyText")
        preparation.setWordWrap(True)
        self.layout.addWidget(preparation)
        settings = QFrame()
        settings.setObjectName("panel")
        form = QFormLayout(settings)
        self.columns = QSpinBox()
        self.columns.setRange(4, 20)
        self.columns.setValue(9)
        self.rows = QSpinBox()
        self.rows.setRange(4, 20)
        self.rows.setValue(6)
        self.square = QDoubleSpinBox()
        self.square.setRange(1.0, 100.0)
        self.square.setValue(25.0)
        self.square.setSuffix(" mm")
        form.addRow("Inner corners across", self.columns)
        form.addRow("Inner corners down", self.rows)
        form.addRow("Measured square size", self.square)
        buttons = QHBoxLayout()
        capture = QPushButton("Capture this view")
        capture.setObjectName("primaryButton")
        capture.clicked.connect(self.capture_requested)
        reset = QPushButton("Clear captured views")
        reset.clicked.connect(self.reset_requested)
        calculate = QPushButton("Calculate and save calibration")
        calculate.clicked.connect(self.calculate_requested)
        load = QPushButton("Load calibration…")
        load.clicked.connect(self.load_requested)
        for button in (capture, reset, calculate, load):
            buttons.addWidget(button)
        buttons.addStretch()
        self.count = StatusCard("Captured views", "0 accepted; 12 minimum")
        row = QHBoxLayout()
        row.addWidget(settings)
        row.addWidget(self.count, 1)
        self.layout.addLayout(row)
        self.layout.addLayout(buttons)
        printables = QHBoxLayout()
        checkerboard = QPushButton("Open printable checkerboard PDF")
        checkerboard.clicked.connect(self.open_checkerboard_requested)
        guide = QPushButton("Open illustrated setup guide")
        guide.clicked.connect(self.open_guide_requested)
        printables.addWidget(checkerboard)
        printables.addWidget(guide)
        printables.addStretch()
        self.layout.addLayout(printables)
        self.message = QLabel(
            "Show the complete board, keep it sharp, and capture 12 genuinely different poses. "
            "Move the board - never the mounted camera."
        )
        self.message.setWordWrap(True)
        self.layout.addWidget(self.message)
        self.canvas = VideoCanvas("Connect the camera first")
        self.layout.addWidget(self.canvas, 1)


class RigCalibrationPage(WizardPage):
    freeze_requested = Signal()
    solve_requested = Signal()
    capture_object_view_requested = Signal()
    save_requested = Signal()
    load_requested = Signal()
    open_guide_requested = Signal()
    interaction_event = Signal(object)

    LANDMARK_NAMES = [
        "LEFT outer edge - TOP mark",
        "LEFT outer edge - BOTTOM mark",
        "CENTER seam - TOP mark",
        "CENTER seam - BOTTOM mark",
        "RIGHT outer edge - TOP mark",
        "RIGHT outer edge - BOTTOM mark",
    ]

    def __init__(self) -> None:
        super().__init__(
            "3. Build and calibrate the scanning corner",
            "This is a large physical fixture, not the checkerboard: two equal-width, rigid, plain matte-white panels "
            "standing upright as an inside V, open toward the camera.",
        )
        preparation = QLabel(
            "First image: remove the object, turn the laser off, and frame the complete left outer edge, "
            "center seam, and right outer edge from their top marks to bottom marks. After solving, place the object "
            "without moving the camera or V, capture a second image, then draw its green scan box."
        )
        preparation.setObjectName("safetyText")
        preparation.setWordWrap(True)
        self.layout.addWidget(preparation)
        self.clicks: list[tuple[float, float]] = []
        self.frozen_frame: np.ndarray | None = None
        geometry = QFrame()
        geometry.setObjectName("panel")
        form = QFormLayout(geometry)
        self.wing_width = QDoubleSpinBox()
        self.wing_width.setRange(50.0, 2000.0)
        self.wing_width.setValue(300.0)
        self.wing_width.setSuffix(" mm")
        self.height = QDoubleSpinBox()
        self.height.setRange(50.0, 2000.0)
        self.height.setValue(400.0)
        self.height.setSuffix(" mm")
        self.angle = QDoubleSpinBox()
        self.angle.setRange(30.0, 150.0)
        self.angle.setValue(90.0)
        self.angle.setSuffix("°")
        form.addRow("Each equal wing width", self.wing_width)
        form.addRow("Corner inside angle", self.angle)
        form.addRow("Exact top-to-bottom mark height", self.height)
        self.prompt = StatusCard("Next landmark", "Freeze the image to begin")
        self.diagram = CornerLandmarkDiagram()
        row = QHBoxLayout()
        row.addWidget(geometry, 2)
        row.addWidget(self.prompt, 1)
        row.addWidget(self.diagram, 2)
        self.layout.addLayout(row)
        buttons = QHBoxLayout()
        freeze = QPushButton("Freeze this view for six clicks")
        freeze.setObjectName("primaryButton")
        freeze.clicked.connect(self.freeze_requested)
        self.undo = QPushButton("Undo point")
        self.undo.clicked.connect(self.undo_point)
        restart = QPushButton("Restart six points")
        restart.clicked.connect(self.reset_points)
        solve = QPushButton("Solve corner pose")
        solve.clicked.connect(self.solve_requested)
        self.capture_object = QPushButton("Capture object view for green box")
        self.capture_object.clicked.connect(self.capture_object_view_requested)
        self.capture_object.setEnabled(False)
        save = QPushButton("Save setup…")
        save.clicked.connect(self.save_requested)
        load = QPushButton("Load setup…")
        load.clicked.connect(self.load_requested)
        for button in (freeze, self.undo, restart, solve, self.capture_object, save, load):
            buttons.addWidget(button)
        buttons.addStretch()
        self.layout.addLayout(buttons)
        self.canvas = VideoCanvas("Freeze an image, then click the reference landmarks")
        self.canvas.point_clicked.connect(self.add_point)
        self.canvas.roi_changed.connect(self._roi_changed)
        self.canvas.interaction_event.connect(self.interaction_event)
        view_buttons = QHBoxLayout()
        guide = QPushButton("Open illustrated setup guide")
        guide.clicked.connect(self.open_guide_requested)
        fit = QPushButton("Fit image")
        fit.clicked.connect(self.canvas.reset_view)
        zoom_out = QPushButton("Zoom out")
        zoom_out.clicked.connect(self.canvas.zoom_out)
        zoom_in = QPushButton("Zoom in")
        zoom_in.clicked.connect(self.canvas.zoom_in)
        view_buttons.addWidget(guide)
        view_buttons.addStretch()
        view_buttons.addWidget(
            QLabel("Wheel zooms at the pointer; drag with left/right/middle to pan; a short left-click marks.")
        )
        view_buttons.addWidget(fit)
        view_buttons.addWidget(zoom_out)
        view_buttons.addWidget(zoom_in)
        self.layout.addLayout(view_buttons)
        self.layout.addWidget(self.canvas, 1)
        self.roi: tuple[int, int, int, int] | None = None
        self.roi_note = QLabel(
            "After solving: place the object, click ‘Capture object view for green box,’ then drag a tight green rectangle around it."
        )
        self.roi_note.setWordWrap(True)
        self.layout.addWidget(self.roi_note)

    def begin_clicking(self, frame: np.ndarray) -> None:
        self.frozen_frame = frame.copy()
        self.capture_object.setEnabled(False)
        self.reset_points()
        self.canvas.reset_view()
        self.canvas.set_frame(self.frozen_frame)

    def add_point(self, x: float, y: float) -> None:
        if self.frozen_frame is None or len(self.clicks) >= 6:
            return
        self.clicks.append((x, y))
        self.canvas.set_landmarks(self.clicks)
        self._update_prompt()
        if len(self.clicks) == 6:
            self.canvas.set_interaction_mode("none")

    def undo_point(self) -> None:
        if self.clicks:
            removed = self.clicks.pop()
            self.canvas.set_landmarks(self.clicks)
            self.canvas.set_interaction_mode("point")
            self._update_prompt()
            self.interaction_event.emit(
                {
                    "action": "point_undone",
                    "removed_image_x": round(removed[0], 3),
                    "removed_image_y": round(removed[1], 3),
                    "remaining_points": len(self.clicks),
                }
            )

    def reset_points(self) -> None:
        removed_count = len(self.clicks)
        self.clicks.clear()
        self.canvas.set_landmarks([])
        self.canvas.set_interaction_mode("point" if self.frozen_frame is not None else "none")
        self._update_prompt()
        if removed_count:
            self.interaction_event.emit(
                {"action": "points_reset", "removed_points": removed_count}
            )

    def _update_prompt(self) -> None:
        if len(self.clicks) < 6:
            self.prompt.set_status(
                f"Point {len(self.clicks) + 1} of 6: click {self.LANDMARK_NAMES[len(self.clicks)]}",
                "warning",
            )
        else:
            self.prompt.set_status("All six points captured—solve the pose", "good")

    def await_object_view(self) -> None:
        self.capture_object.setEnabled(True)
        self.frozen_frame = None
        self.canvas.set_landmarks([])
        self.canvas.set_interaction_mode("none")
        self.roi_note.setText(
            "Corner solved. The preview is live again: place the object without moving the camera or V, then click "
            "‘Capture object view for green box.’"
        )

    def begin_roi(
        self,
        frame: np.ndarray,
        roi: tuple[int, int, int, int],
        polygons: list[np.ndarray],
    ) -> None:
        self.frozen_frame = frame.copy()
        self.roi = roi
        self.canvas.reset_view()
        self.canvas.set_frame(self.frozen_frame, polygons=polygons, roi=roi)
        self.canvas.set_landmarks([])
        self.canvas.set_interaction_mode("roi")
        self.roi_note.setText(
            "Drag a tight rectangle around the object. Keep visible wall stripe outside the rectangle on both sides."
        )
        self.canvas.update()

    def _roi_changed(self, roi: object) -> None:
        self.roi = tuple(roi)  # type: ignore[arg-type]
        self.roi_note.setText(f"Object area: x={self.roi[0]}, y={self.roi[1]}, {self.roi[2]} × {self.roi[3]} px")


class LaserTunePage(WizardPage):
    background_requested = Signal()
    settings_changed = Signal()
    auto_suggest_requested = Signal()
    defaults_restored = Signal()

    DEFAULTS = (120, 45, 55)

    def __init__(self) -> None:
        super().__init__(
            "4. Tune the red laser",
            "Keep the object, camera, and room lighting exactly as they will be during the scan. Turn only the laser OFF "
            "for the 15-frame background, then turn it on and tune for one thin continuous detected trace.",
        )
        lighting = QLabel(
            "Room lights may be ON or OFF, but they must stay at the same level for the background and the scan. "
            "Do not change exposure, focus, gain, white balance, camera position, or the object after capture."
        )
        lighting.setObjectName("safetyText")
        lighting.setWordWrap(True)
        lighting.setMaximumWidth(1000)
        self.layout.addWidget(lighting)
        button_row = QHBoxLayout()
        capture = QPushButton("Capture 15 laser-off frames")
        capture.setObjectName("primaryButton")
        capture.clicked.connect(self.background_requested)
        button_row.addWidget(capture)
        self.background_status = QLabel("No background captured")
        button_row.addWidget(self.background_status)
        button_row.addStretch()
        self.layout.addLayout(button_row)
        controls = QFrame()
        controls.setObjectName("panel")
        form = QGridLayout(controls)
        self.minimum_red, self.minimum_red_value, minimum_red_control = self._slider_control(
            0,
            255,
            self.DEFAULTS[0],
            "Higher rejects dim reddish noise; lower keeps a weak stripe on dark material.",
        )
        self.dominance, self.dominance_value, dominance_control = self._slider_control(
            0,
            180,
            self.DEFAULTS[1],
            "How much stronger red must be than green or blue. Higher rejects white/orange highlights.",
        )
        self.threshold, self.threshold_value, threshold_control = self._slider_control(
            0,
            180,
            self.DEFAULTS[2],
            "How much the laser-on pixel must differ from the saved laser-off scene. Higher rejects static/flicker.",
        )
        form.addWidget(QLabel("Minimum red brightness"), 0, 0)
        form.addWidget(QLabel("Red over other colors"), 0, 1)
        form.addWidget(QLabel("Change from laser-off background"), 0, 2)
        form.addWidget(minimum_red_control, 1, 0)
        form.addWidget(dominance_control, 1, 1)
        form.addWidget(threshold_control, 1, 2)
        tuning_buttons = QHBoxLayout()
        self.auto_suggest = QPushButton("Auto-suggest from laser-on view")
        self.auto_suggest.setToolTip(
            "Estimate conservative starting values from the live frame and saved laser-off background; verify the overlay afterward."
        )
        self.auto_suggest.clicked.connect(self.auto_suggest_requested)
        restore = QPushButton("Restore defaults (120 / 45 / 55)")
        restore.clicked.connect(self.restore_defaults)
        tuning_buttons.addWidget(self.auto_suggest)
        tuning_buttons.addWidget(restore)
        tuning_buttons.addStretch()
        form.addLayout(tuning_buttons, 2, 0, 1, 3)
        self.layout.addWidget(controls)
        goal = QLabel(
            "Goal: very few stray dots and one narrow trace across left wall, object, and right wall. Dashed cyan outlines "
            "are wall regions and the dashed green box is the object region—not detected laser. Detected wall samples are "
            "cyan; detected object samples are green. A thick glow/high saturation should be fixed with lower camera "
            "exposure or gain, laser optics/power, and matte surfaces—not high sharpness."
        )
        goal.setWordWrap(True)
        goal.setMaximumWidth(1000)
        self.layout.addWidget(goal)
        self.quality = StatusCard("Laser detection", "Waiting for camera and calibration")
        self.layout.addWidget(self.quality)
        self.canvas = VideoCanvas("Complete camera and corner calibration first")
        self.layout.addWidget(self.canvas, 1)

    def _slider_control(
        self, minimum: int, maximum: int, value: int, help_text: str
    ) -> tuple[QSlider, QLabel, QWidget]:
        container = QWidget()
        container.setMaximumWidth(325)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        value_row = QHBoxLayout()
        slider = QSlider(Qt.Horizontal)
        slider.setRange(minimum, maximum)
        slider.setValue(value)
        number = QLabel(str(value))
        number.setMinimumWidth(32)
        number.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        slider.valueChanged.connect(lambda current, label=number: label.setText(str(current)))
        slider.valueChanged.connect(self.settings_changed)
        value_row.addWidget(slider, 1)
        value_row.addWidget(number)
        help_label = QLabel(help_text)
        help_label.setWordWrap(True)
        help_label.setObjectName("fieldHelp")
        layout.addLayout(value_row)
        layout.addWidget(help_label)
        return slider, number, container

    def restore_defaults(self) -> None:
        self.apply_settings(LaserSettings())
        self.defaults_restored.emit()

    def apply_settings(self, settings: LaserSettings) -> None:
        values = (
            (self.minimum_red, self.minimum_red_value, settings.minimum_red),
            (self.dominance, self.dominance_value, settings.minimum_dominance),
            (self.threshold, self.threshold_value, int(round(settings.threshold))),
        )
        for slider, label, value in values:
            previous = slider.blockSignals(True)
            slider.setValue(int(value))
            slider.blockSignals(previous)
            label.setText(str(int(value)))
        self.settings_changed.emit()


class ScanPage(WizardPage):
    start_requested = Signal()
    pause_requested = Signal()
    finish_requested = Signal()
    clear_requested = Signal()
    diagnostics_requested = Signal()
    preview_mode_changed = Signal(str)

    def __init__(self) -> None:
        super().__init__(
            "5. Scan the object",
            "Sweep the horizontal line slowly from top to bottom. A frame is accepted only when the same stripe is visible on both reference wings. "
            "Pausing or sweeping backward is safe; invalid frames are kept out of the model. Move only the laser line—not the object.",
        )
        stationary = QLabel(
            "Keep the object, camera, and white V completely stationary for the entire scan. Pausing does not track or align a moved object; "
            "rotating it and resuming would create overlapping or ghosted geometry. Finish this side and make a separate scan for another side."
        )
        stationary.setObjectName("safetyText")
        stationary.setWordWrap(True)
        stationary.setMaximumWidth(1000)
        self.layout.addWidget(stationary)
        buttons = QHBoxLayout()
        self.start = QPushButton("Start scan")
        self.start.setObjectName("primaryButton")
        self.start.clicked.connect(self.start_requested)
        self.pause = QPushButton("Pause")
        self.pause.clicked.connect(self.pause_requested)
        self.finish = QPushButton("Finish and review")
        self.finish.clicked.connect(self.finish_requested)
        self.clear = QPushButton("Clear scan")
        self.clear.clicked.connect(self.clear_requested)
        for button in (self.start, self.pause, self.finish, self.clear):
            buttons.addWidget(button)
        buttons.addStretch()
        self.layout.addLayout(buttons)
        cards = QHBoxLayout()
        self.reference = StatusCard("Reference lock")
        self.laser = StatusCard("Laser plane")
        self.coverage = StatusCard("Captured data", "0 frames • 0 points")
        cards.addWidget(self.reference)
        cards.addWidget(self.laser)
        cards.addWidget(self.coverage)
        self.layout.addLayout(cards)
        splitter = QSplitter()
        self.canvas = VideoCanvas("Start the camera to scan")
        self.cloud = PointCloudView()
        splitter.addWidget(self.canvas)
        splitter.addWidget(self.cloud)
        splitter.setSizes([700, 430])
        self.layout.addWidget(splitter, 1)
        preview_row = QHBoxLayout()
        preview_row.addWidget(QLabel("3D preview colors"))
        self.preview_colors = QComboBox()
        self.preview_colors.addItem("High contrast (recommended)", "high_contrast")
        self.preview_colors.addItem("Measured surface colors", "surface")
        self.preview_colors.currentIndexChanged.connect(self._preview_color_changed)
        preview_row.addWidget(self.preview_colors)
        self.preview_note = QLabel("Display only—saved projects and exported point colors never change.")
        self.preview_note.setWordWrap(True)
        preview_row.addWidget(self.preview_note)
        preview_row.addStretch()
        self.save_diagnostics = QPushButton("Save diagnostics ZIP…")
        self.save_diagnostics.clicked.connect(self.diagnostics_requested)
        self.save_diagnostics.setToolTip(
            "Saves the session event log and settings; you choose whether the current frame and laser-off background are included."
        )
        preview_row.addWidget(self.save_diagnostics)
        self.layout.addLayout(preview_row)
        self.guidance = QLabel("Ready when calibration and background are complete.")
        self.guidance.setObjectName("guidance")
        self.guidance.setWordWrap(True)
        self.layout.addWidget(self.guidance)
        self.diagnostics_note = QLabel(
            "Diagnostics include the event log and settings. You choose whether to include camera images; point clouds are never included. Review before sharing."
        )
        self.diagnostics_note.setWordWrap(True)
        self.diagnostics_note.setObjectName("fieldHelp")
        self.diagnostics_note.setMaximumWidth(1000)
        self.layout.addWidget(self.diagnostics_note)
        self._scan_state = "ready"
        self._has_scan_data = False
        self.set_scan_state("ready", has_data=False)

    @property
    def scan_state(self) -> str:
        return self._scan_state

    def set_scan_state(self, state: str, *, has_data: bool | None = None) -> None:
        """Keep scan controls consistent with the controller's actual state."""

        if state not in {"ready", "scanning", "paused", "finishing", "error"}:
            raise ValueError(f"Unknown scan state: {state}")
        if has_data is not None:
            self._has_scan_data = bool(has_data)
        self._scan_state = state

        if state == "scanning":
            self.start.setText("Scanning…")
            self.start.setEnabled(False)
            self.pause.setEnabled(True)
            self.finish.setEnabled(True)
            self.clear.setEnabled(False)
        elif state == "paused":
            self.start.setText("Resume scan")
            self.start.setEnabled(True)
            self.pause.setEnabled(False)
            self.finish.setEnabled(self._has_scan_data)
            self.clear.setEnabled(self._has_scan_data)
        elif state == "finishing":
            self.start.setText("Finishing…")
            self.start.setEnabled(False)
            self.pause.setEnabled(False)
            self.finish.setEnabled(False)
            self.clear.setEnabled(False)
        else:
            self.start.setText("Try scan again" if state == "error" else "Start scan")
            self.start.setEnabled(True)
            self.pause.setEnabled(False)
            self.finish.setEnabled(self._has_scan_data)
            self.clear.setEnabled(self._has_scan_data)

    def mark_scan_cleared(self) -> None:
        self.set_scan_state("ready", has_data=False)

    def _preview_color_changed(self, _index: int = -1) -> None:
        mode = str(self.preview_colors.currentData())
        self.cloud.set_color_mode(mode)
        self.preview_mode_changed.emit(mode)

    def show_quality(self, quality: FrameQuality, accepted: int, point_count: int, dropped: int) -> None:
        if accepted > 0 or point_count > 0:
            self._has_scan_data = True
            if self._scan_state != "scanning":
                self.set_scan_state(self._scan_state, has_data=True)
        ref_good = quality.left_reference_points > 0 and quality.right_reference_points > 0
        span_text = ""
        if quality.plane_left_span_mm is not None and quality.plane_right_span_mm is not None:
            span_text = (
                f" • spans {quality.plane_left_span_mm:.0f}/{quality.plane_right_span_mm:.0f} mm"
            )
        self.reference.set_status(
            f"Left {quality.left_reference_points} • Right {quality.right_reference_points}{span_text}",
            "good" if ref_good else "bad",
        )
        if quality.plane_rms_mm is None:
            support = (
                f" • attempted support {quality.support_ratio:.5f}"
                if quality.support_ratio is not None
                else ""
            )
            self.laser.set_status(f"No stable plane{support}", "bad")
        else:
            support = (
                f" • support {quality.support_ratio:.5f}"
                if quality.support_ratio is not None
                else ""
            )
            angle = (
                f" • angle {quality.median_triangulation_angle_deg:.1f}°"
                if quality.median_triangulation_angle_deg is not None
                else ""
            )
            self.laser.set_status(
                f"Fit RMS {quality.plane_rms_mm:.2f} mm{support}{angle}",
                "good" if quality.accepted else "warning",
            )
        self.coverage.set_status(
            f"{accepted} accepted frames • {point_count:,} points • {dropped} preview frames dropped",
            "good" if accepted else "neutral",
        )
        self.guidance.setText(quality.message)
        self.guidance.setProperty("accepted", quality.accepted)
        self.guidance.style().unpolish(self.guidance)
        self.guidance.style().polish(self.guidance)


class ReviewPage(WizardPage):
    clean_requested = Signal()
    mesh_requested = Signal()
    save_project_requested = Signal()
    export_ply_requested = Signal()
    export_obj_requested = Signal()
    export_stl_requested = Signal()

    def __init__(self) -> None:
        super().__init__(
            "6. Review and export",
            "The point cloud is the measured result. Cleanup is non-destructive in the saved project. Surface creation makes an open mesh of the camera-visible side; hidden geometry is not fabricated.",
        )
        self.cloud: PointCloud | None = None
        self.mesh: Mesh | None = None
        actions = QHBoxLayout()
        clean = QPushButton("Remove isolated dots")
        clean.clicked.connect(self.clean_requested)
        mesh = QPushButton("Create surface mesh")
        mesh.clicked.connect(self.mesh_requested)
        save = QPushButton("Save .llscan project…")
        save.clicked.connect(self.save_project_requested)
        actions.addWidget(clean)
        actions.addWidget(mesh)
        actions.addWidget(save)
        actions.addStretch()
        self.layout.addLayout(actions)
        exports = QHBoxLayout()
        ply = QPushButton("Export PLY point cloud…")
        ply.setObjectName("primaryButton")
        ply.clicked.connect(self.export_ply_requested)
        self.obj = QPushButton("Export OBJ mesh…")
        self.obj.clicked.connect(self.export_obj_requested)
        self.stl = QPushButton("Export STL mesh…")
        self.stl.clicked.connect(self.export_stl_requested)
        exports.addWidget(ply)
        exports.addWidget(self.obj)
        exports.addWidget(self.stl)
        exports.addStretch()
        self.layout.addLayout(exports)
        self.summary = StatusCard("Model summary", "No scan loaded")
        self.layout.addWidget(self.summary)
        self.viewer = PointCloudView()
        self.layout.addWidget(self.viewer, 1)
        note = QLabel(
            "PLY preserves measured points and colour. OBJ works well in Blender. STL stores triangles without units; "
            "coordinates are written in millimetres, so choose mm when importing into FreeCAD or OpenSCAD."
        )
        note.setWordWrap(True)
        self.layout.addWidget(note)
        self.set_model(None, None)

    def set_model(self, cloud: PointCloud | None, mesh: Mesh | None) -> None:
        self.cloud, self.mesh = cloud, mesh
        self.obj.setEnabled(mesh is not None and bool(len(mesh.faces)))
        self.stl.setEnabled(mesh is not None and bool(len(mesh.faces)))
        if cloud is None or not len(cloud.points):
            self.summary.set_status("No scan loaded", "neutral")
            self.viewer.set_cloud(None)
            return
        minimum, maximum = cloud.bounds or (np.zeros(3), np.zeros(3))
        size = maximum - minimum
        mesh_text = f" • {len(mesh.faces):,} triangles" if mesh is not None else " • no surface yet"
        self.summary.set_status(
            f"{len(cloud.points):,} points{mesh_text} • approximately {size[0]:.1f} × {size[2]:.1f} × {size[1]:.1f} mm (W × D × H)",
            "good",
        )
        self.viewer.set_cloud(cloud)
