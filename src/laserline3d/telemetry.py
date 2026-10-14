"""Bounded, privacy-safe summaries for live scan diagnostics.

The scanner deliberately records measurements rather than camera images here.
Raw frames remain opt-in attachments in the support bundle.
"""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass(slots=True)
class RunningMetric:
    """Keep exact extrema/mean plus a bounded recent distribution sample."""

    count: int = 0
    total: float = 0.0
    minimum: float | None = None
    maximum: float | None = None
    recent: deque[float] = field(default_factory=lambda: deque(maxlen=2048))

    def add(self, value: float | int | None) -> None:
        if value is None:
            return
        number = float(value)
        if not np.isfinite(number):
            return
        self.count += 1
        self.total += number
        self.minimum = number if self.minimum is None else min(self.minimum, number)
        self.maximum = number if self.maximum is None else max(self.maximum, number)
        self.recent.append(number)

    def summary(self) -> dict[str, float | int | None]:
        if not self.count:
            return {
                "count": 0,
                "minimum": None,
                "mean": None,
                "p05_recent": None,
                "median_recent": None,
                "p95_recent": None,
                "maximum": None,
            }
        sample = np.asarray(self.recent, dtype=np.float64)
        return {
            "count": self.count,
            "minimum": self.minimum,
            "mean": self.total / self.count,
            "p05_recent": float(np.percentile(sample, 5.0)),
            "median_recent": float(np.percentile(sample, 50.0)),
            "p95_recent": float(np.percentile(sample, 95.0)),
            "maximum": self.maximum,
        }


class ScanEvidenceAccumulator:
    """Aggregate what the detector saw inside and outside the object ROI.

    This is intentionally bounded: long scans cannot grow the diagnostic data
    in proportion to their duration. Per-frame detail is sampled separately by
    the controller while this class retains complete counts and running ranges.
    """

    CLASS_NAMES = {-1: "unclassified", 0: "left_reference", 1: "object_roi", 2: "right_reference"}

    def __init__(self) -> None:
        self.frames = 0
        self.accepted_frames = 0
        self.rejected_frames = 0
        self.reason_codes: Counter[str] = Counter()
        self.reason_messages: Counter[str] = Counter()
        self.class_point_totals: Counter[str] = Counter()
        self.class_frame_counts: dict[str, RunningMetric] = {
            name: RunningMetric() for name in self.CLASS_NAMES.values()
        }
        self.class_x_spans: dict[str, RunningMetric] = {
            name: RunningMetric() for name in self.CLASS_NAMES.values()
        }
        self.class_y_spans: dict[str, RunningMetric] = {
            name: RunningMetric() for name in self.CLASS_NAMES.values()
        }
        self.class_bounds: dict[str, list[float] | None] = {
            name: None for name in self.CLASS_NAMES.values()
        }
        self.metrics = {
            "detected_points": RunningMetric(),
            "object_points": RunningMetric(),
            "left_reference_points": RunningMetric(),
            "right_reference_points": RunningMetric(),
            "unclassified_points": RunningMetric(),
            "support_ratio": RunningMetric(),
            "plane_rms_mm": RunningMetric(),
            "triangulation_angle_deg": RunningMetric(),
            "saturated_fraction": RunningMetric(),
            "candidate_pixels_inside_roi": RunningMetric(),
            "candidate_pixels_outside_roi": RunningMetric(),
            "candidate_inside_fraction": RunningMetric(),
            "confidence": RunningMetric(),
        }

    def add(self, processed: Any, roi: tuple[int, int, int, int] | None) -> dict[str, Any]:
        quality = processed.quality
        points = np.asarray(processed.detection.points, dtype=np.float64).reshape(-1, 2)
        classes = np.asarray(processed.point_classes, dtype=np.int8).reshape(-1)
        confidence = np.asarray(processed.detection.confidence, dtype=np.float64).reshape(-1)
        self.frames += 1
        if bool(quality.accepted):
            self.accepted_frames += 1
        else:
            self.rejected_frames += 1
        code = str(getattr(quality, "reason_code", "accepted" if quality.accepted else "unspecified"))
        self.reason_codes[code] += 1
        self.reason_messages[str(quality.message)] += 1

        frame_classes: dict[str, dict[str, Any]] = {}
        for class_id, name in self.CLASS_NAMES.items():
            selected = points[classes == class_id]
            count = int(len(selected))
            self.class_point_totals[name] += count
            self.class_frame_counts[name].add(count)
            details: dict[str, Any] = {"count": count, "bounds_px": None, "x_span_px": 0.0, "y_span_px": 0.0}
            if count:
                minimum = selected.min(axis=0)
                maximum = selected.max(axis=0)
                x_span = float(maximum[0] - minimum[0])
                y_span = float(maximum[1] - minimum[1])
                bounds = [float(minimum[0]), float(minimum[1]), float(maximum[0]), float(maximum[1])]
                details.update(bounds_px=bounds, x_span_px=x_span, y_span_px=y_span)
                self.class_x_spans[name].add(x_span)
                self.class_y_spans[name].add(y_span)
                current = self.class_bounds[name]
                self.class_bounds[name] = bounds if current is None else [
                    min(current[0], bounds[0]),
                    min(current[1], bounds[1]),
                    max(current[2], bounds[2]),
                    max(current[3], bounds[3]),
                ]
            frame_classes[name] = details

        candidate_mask = np.asarray(processed.detection.candidate_mask, dtype=bool)
        inside_candidates = 0
        if roi is not None and candidate_mask.ndim == 2:
            height, width = candidate_mask.shape
            x, y, roi_width, roi_height = (int(value) for value in roi)
            x0, y0 = max(0, x), max(0, y)
            x1, y1 = min(width, x + roi_width), min(height, y + roi_height)
            if x1 > x0 and y1 > y0:
                inside_candidates = int(candidate_mask[y0:y1, x0:x1].sum())
        total_candidates = int(candidate_mask.sum()) if candidate_mask.ndim == 2 else 0
        outside_candidates = max(0, total_candidates - inside_candidates)
        inside_fraction = inside_candidates / max(1, total_candidates)

        values = {
            "detected_points": getattr(quality, "detected_points", len(points)),
            "object_points": getattr(quality, "object_points", 0),
            "left_reference_points": getattr(quality, "left_reference_points", 0),
            "right_reference_points": getattr(quality, "right_reference_points", 0),
            "unclassified_points": int((classes == -1).sum()),
            "support_ratio": getattr(quality, "support_ratio", None),
            "plane_rms_mm": getattr(quality, "plane_rms_mm", None),
            "triangulation_angle_deg": getattr(quality, "median_triangulation_angle_deg", None),
            "saturated_fraction": getattr(quality, "saturated_fraction", None),
            "candidate_pixels_inside_roi": inside_candidates,
            "candidate_pixels_outside_roi": outside_candidates,
            "candidate_inside_fraction": inside_fraction,
        }
        for name, value in values.items():
            self.metrics[name].add(value)
        for value in confidence:
            self.metrics["confidence"].add(float(value))

        confidence_summary: dict[str, float | int | None]
        if len(confidence):
            confidence_summary = {
                "count": int(len(confidence)),
                "minimum": float(np.min(confidence)),
                "median": float(np.median(confidence)),
                "p95": float(np.percentile(confidence, 95.0)),
                "maximum": float(np.max(confidence)),
            }
        else:
            confidence_summary = {"count": 0, "minimum": None, "median": None, "p95": None, "maximum": None}
        return {
            "reason_code": code,
            "classes": frame_classes,
            "candidate_pixels": {
                "inside_object_roi": inside_candidates,
                "outside_object_roi": outside_candidates,
                "total": total_candidates,
                "inside_fraction": inside_fraction,
            },
            "confidence": confidence_summary,
        }

    def summary(self) -> dict[str, Any]:
        return {
            "frames": self.frames,
            "accepted_frames": self.accepted_frames,
            "rejected_frames": self.rejected_frames,
            "reason_codes": dict(self.reason_codes),
            "reason_messages": dict(self.reason_messages),
            "class_point_totals": dict(self.class_point_totals),
            "class_bounds_px": self.class_bounds,
            "class_frame_counts": {
                name: metric.summary() for name, metric in self.class_frame_counts.items()
            },
            "class_x_spans_px": {
                name: metric.summary() for name, metric in self.class_x_spans.items()
            },
            "class_y_spans_px": {
                name: metric.summary() for name, metric in self.class_y_spans.items()
            },
            "metrics": {name: metric.summary() for name, metric in self.metrics.items()},
        }
