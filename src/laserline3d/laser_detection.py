"""Background-assisted red laser scoring and subpixel stripe localization."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
from numpy.typing import NDArray

from .models import LaserSettings


@dataclass(slots=True)
class LaserDetection:
    points: NDArray[np.float64]
    confidence: NDArray[np.float64]
    score: NDArray[np.float32]
    candidate_mask: NDArray[np.bool_]
    orientation: str
    saturated_fraction: float


@dataclass(slots=True)
class LaserSettingSuggestion:
    """Conservative starting values estimated from one laser-on frame."""

    settings: LaserSettings
    noise_score: float
    laser_score: float
    separation: float
    median_background_change: float
    sampled_pixels: int


def red_score(
    frame_bgr: NDArray[np.uint8],
    background_bgr: NDArray[np.uint8] | None = None,
) -> NDArray[np.float32]:
    image = frame_bgr.astype(np.float32)
    blue, green, red = cv2.split(image)
    dominance = red - np.maximum(green, blue)
    if background_bgr is not None:
        if background_bgr.shape != frame_bgr.shape:
            raise ValueError("Background frame resolution does not match camera frame")
        baseline = background_bgr.astype(np.float32)
        b0, g0, r0 = cv2.split(baseline)
        delta_red = red - r0
        chroma_change = delta_red - 0.35 * np.maximum(
            np.abs(green - g0), np.abs(blue - b0)
        )
        baseline_dominance = r0 - np.maximum(g0, b0)
        dominance = np.maximum(dominance - baseline_dominance, chroma_change)
    return dominance.astype(np.float32)


def suggest_laser_settings(
    frame_bgr: NDArray[np.uint8],
    background_bgr: NDArray[np.uint8],
    mask: NDArray[np.bool_] | None = None,
) -> LaserSettingSuggestion:
    """Estimate usable thresholds from a laser-on/background image pair.

    The result is intentionally a starting point for visual verification, not
    an automatic calibration. Robust percentiles separate the small bright-red
    population from ordinary camera noise without depending on a camera's
    device-specific exposure scale.
    """

    if frame_bgr.ndim != 3 or frame_bgr.shape[2] != 3:
        raise ValueError("Auto-suggest expects a BGR colour camera frame")
    if background_bgr.shape != frame_bgr.shape:
        raise ValueError("Laser-off background resolution does not match the live frame")
    if mask is None:
        selected = np.ones(frame_bgr.shape[:2], dtype=bool)
    else:
        selected = np.asarray(mask, dtype=bool)
        if selected.shape != frame_bgr.shape[:2]:
            raise ValueError("Auto-suggest mask resolution does not match the live frame")
    if int(selected.sum()) < 100:
        raise ValueError("The calibrated wall/object area is too small for auto-suggest")

    absolute_change = np.abs(
        frame_bgr.astype(np.int16) - background_bgr.astype(np.int16)
    )
    median_background_change = float(np.median(absolute_change[selected]))
    if median_background_change > 15.0:
        raise ValueError(
            "Room lighting or camera exposure changed after the laser-off background. "
            "Restore it or capture the background again before auto-suggest."
        )

    score = red_score(frame_bgr, background_bgr)
    values = score[selected].astype(np.float64)
    noise_score = float(np.percentile(values, 98.0))
    laser_score = float(np.percentile(values, 99.8))
    separation = laser_score - noise_score
    if laser_score < 12.0 or separation < 8.0:
        raise ValueError(
            "No clearly separated red laser stripe was found. Turn the laser on, keep "
            "it visible on both white wings and the object, then try again."
        )

    threshold = float(np.clip(noise_score + 0.32 * separation, 8.0, 180.0))
    likely_cutoff = max(threshold, float(np.percentile(values, 99.0)))
    likely = selected & (score >= likely_cutoff)
    if int(likely.sum()) < 20:
        raise ValueError("Too few laser pixels were found for a reliable suggestion")

    blue, green, red = cv2.split(frame_bgr)
    raw_dominance = red.astype(np.int16) - np.maximum(green, blue).astype(np.int16)
    minimum_red = int(
        np.clip(np.percentile(red[likely], 15.0) - 8.0, 30.0, 230.0)
    )
    minimum_dominance = int(
        np.clip(np.percentile(raw_dominance[likely], 15.0) - 5.0, 3.0, 180.0)
    )
    return LaserSettingSuggestion(
        settings=LaserSettings(
            minimum_red=minimum_red,
            minimum_dominance=minimum_dominance,
            threshold=float(round(threshold)),
            orientation="horizontal",
            use_background=True,
        ),
        noise_score=noise_score,
        laser_score=laser_score,
        separation=separation,
        median_background_change=median_background_change,
        sampled_pixels=int(selected.sum()),
    )


def _remove_small_components(mask: NDArray[np.bool_], minimum: int) -> NDArray[np.bool_]:
    count, labels, stats, _ = cv2.connectedComponentsWithStats(
        mask.astype(np.uint8), connectivity=8
    )
    keep = np.zeros(count, dtype=bool)
    if count > 1:
        keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= minimum
    return keep[labels]


def _orientation(mask: NDArray[np.bool_], requested: str) -> str:
    if requested != "auto":
        return requested
    ys, xs = np.nonzero(mask)
    if len(xs) < 2:
        return "horizontal"
    return "horizontal" if np.ptp(xs) >= np.ptp(ys) else "vertical"


def _ridge_by_columns(
    score: NDArray[np.float32],
    mask: NDArray[np.bool_],
    half_width: int,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    height, width = score.shape
    points: list[tuple[float, float]] = []
    confidence: list[float] = []
    for x in range(width):
        candidates = np.flatnonzero(mask[:, x])
        if not len(candidates):
            continue
        peak_y = int(candidates[np.argmax(score[candidates, x])])
        y0, y1 = max(0, peak_y - half_width), min(height, peak_y + half_width + 1)
        ys = np.arange(y0, y1, dtype=np.float64)
        weights = np.maximum(score[y0:y1, x].astype(np.float64), 0.0)
        weights *= mask[y0:y1, x]
        total = float(weights.sum())
        if total <= 0.0:
            continue
        sub_y = float(np.sum(ys * weights) / total)
        points.append((float(x), sub_y))
        confidence.append(float(score[peak_y, x]))
    return np.asarray(points, dtype=np.float64).reshape(-1, 2), np.asarray(confidence)


def _ridge_by_rows(
    score: NDArray[np.float32],
    mask: NDArray[np.bool_],
    half_width: int,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    transposed_points, confidence = _ridge_by_columns(
        score.T, mask.T, half_width
    )
    return transposed_points[:, ::-1], confidence


def _continuity_filter(
    points: NDArray[np.float64], confidence: NDArray[np.float64], orientation: str
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    if len(points) < 7:
        return points, confidence
    dependent = points[:, 1] if orientation == "horizontal" else points[:, 0]
    smooth = cv2.medianBlur(dependent.astype(np.float32).reshape(-1, 1), 5).ravel()
    difference = np.abs(dependent - smooth)
    adaptive = max(8.0, float(np.median(difference) + 6.0 * np.median(np.abs(difference - np.median(difference)))))
    keep = difference <= adaptive
    return points[keep], confidence[keep]


def detect_laser(
    frame_bgr: NDArray[np.uint8],
    settings: LaserSettings,
    background_bgr: NDArray[np.uint8] | None = None,
) -> LaserDetection:
    if frame_bgr.ndim != 3 or frame_bgr.shape[2] != 3:
        raise ValueError("Laser detector expects a BGR colour frame")
    background = background_bgr if settings.use_background else None
    score = red_score(frame_bgr, background)
    blue, green, red = cv2.split(frame_bgr)
    raw = (
        (red >= settings.minimum_red)
        & ((red.astype(np.int16) - np.maximum(green, blue).astype(np.int16)) >= settings.minimum_dominance)
        & (score >= settings.threshold)
    )
    opened = cv2.morphologyEx(
        raw.astype(np.uint8),
        cv2.MORPH_OPEN,
        np.ones((2, 2), dtype=np.uint8),
    ).astype(bool)
    candidates = _remove_small_components(opened, settings.minimum_component_px)
    direction = _orientation(candidates, settings.orientation)
    if direction == "horizontal":
        points, confidence = _ridge_by_columns(
            score, candidates, settings.ridge_half_width_px
        )
    else:
        points, confidence = _ridge_by_rows(
            score, candidates, settings.ridge_half_width_px
        )
    points, confidence = _continuity_filter(points, confidence, direction)
    saturated = candidates & (red >= 250)
    saturated_fraction = float(saturated.sum() / max(1, candidates.sum()))
    return LaserDetection(
        points=points,
        confidence=confidence,
        score=score,
        candidate_mask=candidates,
        orientation=direction,
        saturated_fraction=saturated_fraction,
    )


def detection_overlay(
    frame_bgr: NDArray[np.uint8], detection: LaserDetection
) -> NDArray[np.uint8]:
    overlay = frame_bgr.copy()
    for x, y in np.rint(detection.points).astype(np.int32):
        cv2.circle(overlay, (int(x), int(y)), 1, (0, 255, 255), -1)
    return overlay
