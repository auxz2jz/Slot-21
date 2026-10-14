from __future__ import annotations

import math

import cv2
import numpy as np
from numpy.typing import NDArray
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QImage,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QWheelEvent,
)
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QSizePolicy, QVBoxLayout, QWidget

from ..models import Mesh, PointCloud


POINT_CLOUD_PREVIEW_LIMITS = (10_000, 50_000)
DEFAULT_POINT_CLOUD_PREVIEW_LIMIT = POINT_CLOUD_PREVIEW_LIMITS[0]


class VideoCanvas(QWidget):
    point_clicked = Signal(float, float)
    roi_changed = Signal(object)
    interaction_event = Signal(object)

    def __init__(self, placeholder: str = "Camera preview") -> None:
        super().__init__()
        self.setMinimumSize(520, 330)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._placeholder = placeholder
        self._pixmap: QPixmap | None = None
        self._image_size = (0, 0)
        self._display_rect = QRectF()
        self._points = np.empty((0, 2), dtype=np.float64)
        self._classes = np.empty(0, dtype=np.int8)
        self._polygons: list[NDArray[np.float64]] = []
        self._landmarks: list[tuple[float, float]] = []
        self._roi: tuple[int, int, int, int] | None = None
        self._mode = "none"
        self._drag_start: QPointF | None = None
        self._drag_end: QPointF | None = None
        self._view_zoom = 1.0
        self._view_pan = QPointF(0.0, 0.0)
        self._pan_drag_start: QPointF | None = None
        self._pan_drag_origin = QPointF(0.0, 0.0)
        self._active_pan_button: Qt.MouseButton | None = None
        self._left_press_position: QPointF | None = None

    def set_frame(
        self,
        frame_bgr: NDArray[np.uint8],
        *,
        points: NDArray[np.floating] | None = None,
        classes: NDArray[np.integer] | None = None,
        polygons: list[NDArray[np.floating]] | None = None,
        roi: tuple[int, int, int, int] | None = None,
    ) -> None:
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        height, width = rgb.shape[:2]
        if self._image_size != (0, 0) and self._image_size != (width, height):
            self.reset_view()
        image = QImage(rgb.data, width, height, rgb.strides[0], QImage.Format_RGB888).copy()
        self._pixmap = QPixmap.fromImage(image)
        self._image_size = (width, height)
        self._points = (
            np.asarray(points, dtype=np.float64).reshape(-1, 2)
            if points is not None
            else np.empty((0, 2), dtype=np.float64)
        )
        self._classes = (
            np.asarray(classes, dtype=np.int8).reshape(-1)
            if classes is not None
            else np.full(len(self._points), -1, dtype=np.int8)
        )
        self._polygons = [np.asarray(p, dtype=np.float64) for p in (polygons or [])]
        self._roi = roi
        self.update()

    def set_landmarks(self, points: list[tuple[float, float]]) -> None:
        self._landmarks = list(points)
        self.update()

    def set_interaction_mode(self, mode: str) -> None:
        if mode not in {"none", "point", "roi"}:
            raise ValueError(mode)
        self._mode = mode
        self._cancel_pointer_interaction()
        self._restore_cursor()

    @property
    def view_zoom(self) -> float:
        return self._view_zoom

    @property
    def interaction_mode(self) -> str:
        return self._mode

    def view_state(self) -> dict[str, float]:
        """Return non-image view geometry for diagnostics and reproducibility."""

        return {
            "zoom": round(self._view_zoom, 6),
            "pan_x": round(self._view_pan.x(), 3),
            "pan_y": round(self._view_pan.y(), 3),
        }

    def reset_view(self) -> None:
        changed = self._view_zoom != 1.0 or not self._view_pan.isNull()
        self._view_zoom = 1.0
        self._view_pan = QPointF(0.0, 0.0)
        self.update()
        self.interaction_event.emit(
            {
                "action": "view_reset",
                "mode": self._mode,
                "changed": changed,
                "zoom": self._view_zoom,
                "pan_x": 0.0,
                "pan_y": 0.0,
            }
        )

    def zoom_in(self) -> None:
        self._set_view_zoom(
            self._view_zoom * 1.35,
            QPointF(self.width() / 2.0, self.height() / 2.0),
            source="button_in",
        )

    def zoom_out(self) -> None:
        self._set_view_zoom(
            self._view_zoom / 1.35,
            QPointF(self.width() / 2.0, self.height() / 2.0),
            source="button_out",
        )

    def _target_rect(self) -> QRectF:
        if self._image_size[0] <= 0 or self.width() <= 0 or self.height() <= 0:
            return QRectF()
        fitted = _fit_rect(self.width(), self.height(), *self._image_size)
        center = fitted.center() + self._view_pan
        return QRectF(
            center.x() - fitted.width() * self._view_zoom / 2.0,
            center.y() - fitted.height() * self._view_zoom / 2.0,
            fitted.width() * self._view_zoom,
            fitted.height() * self._view_zoom,
        )

    def _set_view_zoom(
        self,
        value: float,
        anchor: QPointF | None = None,
        *,
        source: str = "programmatic",
    ) -> None:
        old_zoom = self._view_zoom
        new_zoom = float(np.clip(value, 1.0, 8.0))
        old_target = self._target_rect()
        anchor = (
            QPointF(anchor)
            if anchor is not None
            else QPointF(self.width() / 2, self.height() / 2)
        )
        image_anchor: tuple[float, float] | None = None
        if not old_target.isEmpty() and old_target.contains(anchor):
            image_anchor = (
                (anchor.x() - old_target.left()) / old_target.width(),
                (anchor.y() - old_target.top()) / old_target.height(),
            )

        self._view_zoom = new_zoom
        if self._view_zoom <= 1.001:
            self._view_pan = QPointF(0.0, 0.0)
        elif image_anchor is not None:
            fitted = _fit_rect(self.width(), self.height(), *self._image_size)
            width = fitted.width() * self._view_zoom
            height = fitted.height() * self._view_zoom
            u, v = image_anchor
            new_center = QPointF(
                anchor.x() - u * width + width / 2.0,
                anchor.y() - v * height + height / 2.0,
            )
            self._view_pan = new_center - fitted.center()
        self.update()
        payload: dict[str, object] = {
            "action": "view_zoom",
            "mode": self._mode,
            "source": source,
            "old_zoom": round(old_zoom, 6),
            "zoom": round(self._view_zoom, 6),
            "anchor_x": round(anchor.x(), 3),
            "anchor_y": round(anchor.y(), 3),
            "pan_x": round(self._view_pan.x(), 3),
            "pan_y": round(self._view_pan.y(), 3),
        }
        if image_anchor is not None:
            payload["image_anchor_u"] = round(image_anchor[0], 6)
            payload["image_anchor_v"] = round(image_anchor[1], 6)
        self.interaction_event.emit(payload)

    def paintEvent(self, _event: object) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#10151d"))
        if self._pixmap is None:
            painter.setPen(QColor("#8290a5"))
            painter.drawText(self.rect(), Qt.AlignCenter, self._placeholder)
            return
        target = self._target_rect()
        self._display_rect = target
        painter.drawPixmap(target.toRect(), self._pixmap)
        sx = target.width() / self._image_size[0]
        sy = target.height() / self._image_size[1]

        def mapped(x: float, y: float) -> QPointF:
            return QPointF(target.left() + x * sx, target.top() + y * sy)

        colors = {
            -1: QColor(145, 155, 170, 180),
            0: QColor(0, 220, 255),
            1: QColor(90, 255, 120),
            2: QColor(0, 220, 255),
        }
        for index, (x, y) in enumerate(self._points[::2]):
            source_index = index * 2
            kind = int(self._classes[source_index]) if source_index < len(self._classes) else -1
            painter.setPen(QPen(colors.get(kind, QColor("#ffd166")), 2.0))
            painter.drawPoint(mapped(float(x), float(y)))
        polygon_colors = [QColor(0, 210, 255, 210), QColor(0, 210, 255, 210)]
        for polygon, color in zip(self._polygons, polygon_colors, strict=False):
            painter.setPen(QPen(color, 2, Qt.DashLine))
            for start, end in zip(polygon, np.roll(polygon, -1, axis=0), strict=True):
                painter.drawLine(mapped(*start), mapped(*end))
        if self._roi is not None:
            x, y, width, height = self._roi
            painter.setPen(QPen(QColor("#65ff82"), 2, Qt.DashLine))
            painter.drawRect(QRectF(mapped(x, y), mapped(x + width, y + height)))
        for index, (x, y) in enumerate(self._landmarks, start=1):
            center = mapped(x, y)
            painter.setBrush(QColor("#ffcc4d"))
            painter.setPen(QPen(QColor("#1b1f27"), 1))
            painter.drawEllipse(center, 9, 9)
            painter.setPen(QColor("#11151b"))
            painter.drawText(QRectF(center.x() - 8, center.y() - 8, 16, 16), Qt.AlignCenter, str(index))
        if self._drag_start is not None and self._drag_end is not None:
            painter.setPen(QPen(QColor("#65ff82"), 2, Qt.DashLine))
            painter.drawRect(QRectF(self._drag_start, self._drag_end).normalized())

    def _to_image(self, position: QPointF) -> tuple[float, float] | None:
        display_rect = self._target_rect()
        self._display_rect = display_rect
        if not display_rect.contains(position) or self._image_size[0] == 0:
            return None
        x = (position.x() - display_rect.left()) * self._image_size[0] / display_rect.width()
        y = (position.y() - display_rect.top()) * self._image_size[1] / display_rect.height()
        return x, y

    def _restore_cursor(self) -> None:
        self.setCursor(Qt.CrossCursor if self._mode != "none" else Qt.ArrowCursor)

    def _cancel_pointer_interaction(self) -> None:
        self._pan_drag_start = None
        self._active_pan_button = None
        self._left_press_position = None
        self._drag_start = None
        self._drag_end = None

    @staticmethod
    def _button_name(button: Qt.MouseButton | None) -> str:
        names = {
            Qt.LeftButton: "left",
            Qt.RightButton: "right",
            Qt.MiddleButton: "middle",
        }
        return names.get(button, "unknown")

    def _start_pan(self, position: QPointF, button: Qt.MouseButton) -> None:
        self._pan_drag_start = QPointF(position)
        self._pan_drag_origin = QPointF(self._view_pan)
        self._active_pan_button = button
        self.setCursor(Qt.ClosedHandCursor)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() in (Qt.RightButton, Qt.MiddleButton) and self._pixmap is not None:
            self._start_pan(event.position(), event.button())
            event.accept()
            return
        if event.button() != Qt.LeftButton:
            return
        image_point = self._to_image(event.position())
        if image_point is None:
            return
        if self._mode == "point":
            self._left_press_position = QPointF(event.position())
            event.accept()
        elif self._mode == "roi":
            self._drag_start = event.position()
            self._drag_end = event.position()
            self.update()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if (
            self._mode == "point"
            and self._left_press_position is not None
            and self._pan_drag_start is None
        ):
            delta = event.position() - self._left_press_position
            threshold = max(4, QApplication.startDragDistance())
            if delta.manhattanLength() >= threshold:
                self._start_pan(self._left_press_position, Qt.LeftButton)
        if self._pan_drag_start is not None:
            delta = event.position() - self._pan_drag_start
            self._view_pan = self._pan_drag_origin + delta
            self.update()
            event.accept()
            return
        if self._mode == "roi" and self._drag_start is not None:
            self._drag_end = event.position()
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._pan_drag_start is not None and event.button() == self._active_pan_button:
            delta = self._view_pan - self._pan_drag_origin
            button = self._active_pan_button
            self._pan_drag_start = None
            self._active_pan_button = None
            self._left_press_position = None
            self._restore_cursor()
            self.interaction_event.emit(
                {
                    "action": "view_pan",
                    "mode": self._mode,
                    "button": self._button_name(button),
                    "delta_x": round(delta.x(), 3),
                    "delta_y": round(delta.y(), 3),
                    "pan_x": round(self._view_pan.x(), 3),
                    "pan_y": round(self._view_pan.y(), 3),
                    "zoom": round(self._view_zoom, 6),
                }
            )
            event.accept()
            return
        if event.button() == Qt.LeftButton and self._mode == "point":
            pressed = self._left_press_position
            self._left_press_position = None
            if pressed is None:
                return
            delta = event.position() - pressed
            threshold = max(4, QApplication.startDragDistance())
            if delta.manhattanLength() >= threshold:
                self._view_pan += delta
                self.update()
                self.interaction_event.emit(
                    {
                        "action": "view_pan",
                        "mode": self._mode,
                        "button": "left",
                        "delta_x": round(delta.x(), 3),
                        "delta_y": round(delta.y(), 3),
                        "pan_x": round(self._view_pan.x(), 3),
                        "pan_y": round(self._view_pan.y(), 3),
                        "zoom": round(self._view_zoom, 6),
                    }
                )
                event.accept()
                return
            image_point = self._to_image(event.position())
            if image_point is not None:
                self.interaction_event.emit(
                    {
                        "action": "point_placed",
                        "mode": self._mode,
                        "image_x": round(image_point[0], 3),
                        "image_y": round(image_point[1], 3),
                        "zoom": round(self._view_zoom, 6),
                    }
                )
                self.point_clicked.emit(*image_point)
            event.accept()
            return
        if self._mode != "roi" or self._drag_start is None or self._drag_end is None:
            return
        self._drag_end = event.position()
        start = self._to_image(self._drag_start)
        end = self._to_image(self._drag_end)
        self._drag_start = self._drag_end = None
        if start is None or end is None:
            self.update()
            return
        x0, x1 = sorted((start[0], end[0]))
        y0, y1 = sorted((start[1], end[1]))
        roi = (int(x0), int(y0), int(x1 - x0), int(y1 - y0))
        if roi[2] >= 10 and roi[3] >= 10:
            self._roi = roi
            self.interaction_event.emit(
                {
                    "action": "roi_selected",
                    "mode": self._mode,
                    "x": roi[0],
                    "y": roi[1],
                    "width": roi[2],
                    "height": roi[3],
                    "zoom": round(self._view_zoom, 6),
                }
            )
            self.roi_changed.emit(roi)
        self.update()

    def wheelEvent(self, event: QWheelEvent) -> None:
        if self._pixmap is None:
            return
        steps = event.angleDelta().y() / 120.0
        self._set_view_zoom(
            self._view_zoom * (1.25**steps),
            event.position(),
            source="wheel",
        )
        event.accept()


class CornerLandmarkDiagram(QWidget):
    """Compact front-view reminder for the six reference-corner clicks."""

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(280, 155)
        self.setToolTip(
            "Front view. Click left outer top/bottom, center seam top/bottom, then right outer top/bottom."
        )

    def paintEvent(self, _event: object) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#121a24"))
        width, height = float(self.width()), float(self.height())
        left_top = QPointF(28.0, 43.0)
        left_bottom = QPointF(28.0, height - 27.0)
        seam_top = QPointF(width / 2.0, 25.0)
        seam_bottom = QPointF(width / 2.0, height - 13.0)
        right_top = QPointF(width - 28.0, 43.0)
        right_bottom = QPointF(width - 28.0, height - 27.0)

        left = QPainterPath(left_top)
        left.lineTo(seam_top)
        left.lineTo(seam_bottom)
        left.lineTo(left_bottom)
        left.closeSubpath()
        painter.fillPath(left, QColor("#24394d"))
        right = QPainterPath(seam_top)
        right.lineTo(right_top)
        right.lineTo(right_bottom)
        right.lineTo(seam_bottom)
        right.closeSubpath()
        painter.fillPath(right, QColor("#1f4146"))

        painter.setPen(QPen(QColor("#00cfe0"), 2.0))
        painter.drawLine(left_top, seam_top)
        painter.drawLine(left_bottom, seam_bottom)
        painter.drawLine(seam_top, right_top)
        painter.drawLine(seam_bottom, right_bottom)
        painter.setPen(QPen(QColor("#d8e3ee"), 2.0))
        painter.drawLine(left_top, left_bottom)
        painter.drawLine(seam_top, seam_bottom)
        painter.drawLine(right_top, right_bottom)

        for index, point in enumerate(
            (left_top, left_bottom, seam_top, seam_bottom, right_top, right_bottom), start=1
        ):
            painter.setBrush(QColor("#ffb51b"))
            painter.setPen(QPen(QColor("#17212b"), 1.0))
            painter.drawEllipse(point, 10.0, 10.0)
            painter.setPen(QColor("#17212b"))
            painter.drawText(
                QRectF(point.x() - 8.0, point.y() - 8.0, 16.0, 16.0),
                Qt.AlignCenter,
                str(index),
            )

        painter.setPen(QColor("#aab8c7"))
        painter.drawText(8, height - 5, "FRONT VIEW - plain matte-white wings")


def _fit_rect(widget_width: int, widget_height: int, image_width: int, image_height: int) -> QRectF:
    scale = min(widget_width / image_width, widget_height / image_height)
    width, height = image_width * scale, image_height * scale
    return QRectF((widget_width - width) / 2, (widget_height - height) / 2, width, height)


class PointCloudView(QWidget):
    point_counts_changed = Signal(int, int)

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(420, 320)
        self._source_points = np.empty((0, 3), dtype=np.float64)
        self._source_colors = np.empty((0, 3), dtype=np.uint8)
        self._points = np.empty((0, 3), dtype=np.float64)
        self._colors = np.empty((0, 3), dtype=np.uint8)
        self._point_limit = DEFAULT_POINT_CLOUD_PREVIEW_LIMIT
        self._yaw = -0.55
        self._pitch = 0.35
        self._zoom = 1.0
        self._last_position: QPoint | None = None
        self._color_mode = "high_contrast"

    def set_cloud(self, cloud: PointCloud | None) -> None:
        if cloud is None or not len(cloud.points):
            self._source_points = np.empty((0, 3), dtype=np.float64)
            self._source_colors = np.empty((0, 3), dtype=np.uint8)
        else:
            # Keep read-only source references so changing preview detail can
            # resample without touching the measured cloud or its RGB values.
            self._source_points = cloud.points
            self._source_colors = cloud.colors
        self._resample_preview()

    def _resample_preview(self) -> None:
        total = len(self._source_points)
        if not total:
            self._points = np.empty((0, 3), dtype=np.float64)
            self._colors = np.empty((0, 3), dtype=np.uint8)
        elif total <= self._point_limit:
            self._points = self._source_points.copy()
            self._colors = self._source_colors.copy()
        else:
            indices = np.linspace(0, total - 1, self._point_limit, dtype=np.int64)
            self._points = self._source_points[indices].copy()
            self._colors = self._source_colors[indices].copy()
        self.point_counts_changed.emit(len(self._points), total)
        self.update()

    @property
    def point_limit(self) -> int:
        return self._point_limit

    @property
    def source_point_count(self) -> int:
        return len(self._source_points)

    @property
    def displayed_point_count(self) -> int:
        return len(self._points)

    @property
    def point_count_text(self) -> str:
        return f"Showing {self.displayed_point_count:,} of {self.source_point_count:,} points"

    def set_point_limit(self, point_limit: int) -> None:
        """Change preview detail only; measured/exported cloud data is untouched."""

        point_limit = int(point_limit)
        if point_limit not in POINT_CLOUD_PREVIEW_LIMITS:
            choices = ", ".join(f"{value:,}" for value in POINT_CLOUD_PREVIEW_LIMITS)
            raise ValueError(f"Preview point limit must be one of: {choices}")
        if point_limit == self._point_limit:
            return
        self._point_limit = point_limit
        self._resample_preview()

    def set_mesh(self, mesh: Mesh | None) -> None:
        if mesh is None:
            self.set_cloud(None)
        else:
            self.set_cloud(PointCloud(mesh.vertices, mesh.colors, np.zeros((len(mesh.vertices), 2))))

    @property
    def color_mode(self) -> str:
        return self._color_mode

    def set_color_mode(self, mode: str) -> None:
        """Select preview-only color handling without modifying scan/export data."""

        if mode not in {"high_contrast", "surface"}:
            raise ValueError(f"Unknown point-cloud color mode: {mode}")
        self._color_mode = mode
        self.update()

    def _colors_for_display(self) -> NDArray[np.uint8]:
        if self._color_mode == "surface" or not len(self._colors):
            return self._colors
        colors = self._colors.astype(np.float64)
        peak = colors.max(axis=1)
        scale = np.maximum(1.0, 145.0 / np.maximum(peak, 1.0))
        lifted = np.clip(colors * scale[:, None], 0.0, 255.0)
        nearly_black = peak < 12.0
        lifted[nearly_black] = np.array([190.0, 220.0, 240.0])
        return np.rint(lifted).astype(np.uint8)

    def paintEvent(self, _event: object) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#0e141c"))
        if not len(self._points):
            painter.setPen(QColor("#8391a5"))
            painter.drawText(self.rect(), Qt.AlignCenter, "3D preview appears here")
            painter.drawText(12, self.height() - 12, self.point_count_text)
            return
        centered = self._points - self._points.mean(axis=0)
        cy, sy = math.cos(self._yaw), math.sin(self._yaw)
        cp, sp = math.cos(self._pitch), math.sin(self._pitch)
        yaw = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
        pitch = np.array([[1, 0, 0], [0, cp, -sp], [0, sp, cp]])
        rotated = centered @ (pitch @ yaw).T
        span = max(float(np.ptp(rotated[:, 0])), float(np.ptp(rotated[:, 1])), 1e-6)
        scale = 0.82 * min(self.width(), self.height()) / span * self._zoom
        screen_x = self.width() / 2 + rotated[:, 0] * scale
        screen_y = self.height() / 2 - rotated[:, 1] * scale
        order = np.argsort(rotated[:, 2])
        display_colors = self._colors_for_display()
        for index in order:
            color = display_colors[index]
            painter.setPen(QColor(int(color[0]), int(color[1]), int(color[2]), 220))
            painter.drawPoint(QPointF(float(screen_x[index]), float(screen_y[index])))
        painter.setPen(QColor("#748197"))
        painter.drawText(12, 22, "Drag to rotate • wheel to zoom")
        if self._color_mode == "high_contrast":
            painter.drawText(12, 40, "High-contrast preview • saved RGB is unchanged")
        painter.drawText(12, self.height() - 12, self.point_count_text)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self._last_position = event.position().toPoint()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._last_position is None:
            return
        current = event.position().toPoint()
        delta = current - self._last_position
        self._last_position = current
        self._yaw += delta.x() * 0.01
        self._pitch = float(np.clip(self._pitch + delta.y() * 0.01, -1.5, 1.5))
        self.update()

    def mouseReleaseEvent(self, _event: QMouseEvent) -> None:
        self._last_position = None

    def wheelEvent(self, event: QWheelEvent) -> None:
        self._zoom = float(np.clip(self._zoom * (1.12 ** (event.angleDelta().y() / 120)), 0.2, 8.0))
        self.update()


class StatusCard(QFrame):
    def __init__(self, title: str, text: str = "Not ready") -> None:
        super().__init__()
        self.setObjectName("statusCard")
        layout = QVBoxLayout(self)
        self.title = QLabel(title)
        self.title.setObjectName("cardTitle")
        self.value = QLabel(text)
        self.value.setWordWrap(True)
        layout.addWidget(self.title)
        layout.addWidget(self.value)

    def set_status(self, text: str, level: str = "neutral") -> None:
        colors = {
            "neutral": "#9aa8bb",
            "good": "#6de58b",
            "warning": "#ffd166",
            "bad": "#ff6b72",
        }
        self.value.setText(text)
        self.value.setStyleSheet(f"color: {colors.get(level, colors['neutral'])};")
