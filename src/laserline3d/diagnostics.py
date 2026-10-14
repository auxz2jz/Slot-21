"""Structured diagnostics that preserve the first useful failure."""

from __future__ import annotations

import json
import logging
import math
import os
import platform
import re
import sys
import tempfile
import threading
import time
import traceback
import uuid
import zipfile
from collections import Counter, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import cv2
import numpy as np


MAX_FRAME_STATISTICS_PIXELS = 200_000


class DiagnosticLog:
    """Thread-safe, bounded JSONL action trace for one application session."""

    MAX_SESSION_LOGS = 20
    MAX_STORED_LOG_BYTES = 48 * 1024 * 1024
    MAX_LOG_BYTES = 8 * 1024 * 1024
    MAX_EVENT_BYTES = 64 * 1024
    MAX_RECENT_EVENTS = 1000
    MAX_FAILURE_EVENTS = 100
    MAX_TRACKED_EVENT_TYPES = 256
    MAX_ATTACHMENT_COUNT = 8
    MAX_ATTACHMENT_BYTES = 16 * 1024 * 1024
    MAX_TOTAL_ATTACHMENT_BYTES = 32 * 1024 * 1024
    MAX_SUPPORT_BUNDLE_BYTES = 42 * 1024 * 1024

    def __init__(
        self,
        directory: Path | None = None,
        *,
        app_version: str = "unknown",
        max_log_bytes: int | None = None,
    ) -> None:
        local_data = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
        root = directory or local_data / "LaserLine3D" / "diagnostics"
        root.mkdir(parents=True, exist_ok=True)
        self.session_id = str(uuid.uuid4())
        self.app_version = str(app_version)
        self._started_monotonic = time.monotonic()
        self._sequence = 0
        self._lock = threading.RLock()
        requested_limit = self.MAX_LOG_BYTES if max_log_bytes is None else int(max_log_bytes)
        self.max_log_bytes = max(2048, requested_limit)
        self._compact_target_bytes = max(1024, self.max_log_bytes // 2)
        self._recent_events: deque[dict[str, Any]] = deque(
            maxlen=self.MAX_RECENT_EVENTS
        )
        self._failure_events: deque[dict[str, Any]] = deque(
            maxlen=self.MAX_FAILURE_EVENTS
        )
        self._event_counts: Counter[str] = Counter()
        self._latest_by_event: dict[str, dict[str, Any]] = {}
        self._first_event: dict[str, Any] | None = None
        self._first_failure: dict[str, Any] | None = None
        self._compaction_count = 0
        self._first_failure_written = False
        self._prune_old_session_logs(root)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        self.path = root / f"laserline3d_{stamp}_{self.session_id[:8]}.jsonl"
        self.event(
            "application_started",
            state="running",
            result="ok",
            python=sys.version,
            packaged_application=bool(getattr(sys, "frozen", False)),
        )

    def _prune_old_session_logs(self, root: Path) -> None:
        """Keep diagnostic storage bounded while preserving recent sessions.

        Count and aggregate-byte limits are both necessary: a prior version
        could create a single log larger than 150 MB during a long scan.
        Failures here must never prevent the scanner from starting.
        """

        logs: list[Path] = []
        for path in root.glob("laserline3d_*.jsonl"):
            try:
                path.stat()
            except OSError:
                continue
            logs.append(path)
        logs.sort(key=lambda path: path.stat().st_mtime)
        remove_count = max(0, len(logs) - (self.MAX_SESSION_LOGS - 1))
        for old_log in logs[:remove_count]:
            try:
                old_log.unlink()
            except OSError:
                # Logging must never prevent the scanner from starting.
                pass
        remaining = [path for path in logs[remove_count:] if path.exists()]
        try:
            total_bytes = sum(path.stat().st_size for path in remaining)
        except OSError:
            return
        # Reserve room for the session that is about to start. Oldest evidence
        # is removed first; recent bounded logs remain available for support.
        storage_budget = max(0, self.MAX_STORED_LOG_BYTES - self.max_log_bytes)
        for old_log in remaining:
            if total_bytes <= storage_budget:
                break
            try:
                size = old_log.stat().st_size
                old_log.unlink()
                total_bytes -= size
            except OSError:
                pass

    def event(
        self,
        name: str,
        *,
        action: str | None = None,
        request: str | None = None,
        state: str | None = None,
        result: str | None = None,
        failure: BaseException | str | None = None,
        test_result: str | None = None,
        **details: Any,
    ) -> str:
        with self._lock:
            self._sequence += 1
            event_id = str(uuid.uuid4())
            record: dict[str, Any] = {
                "event_id": event_id,
                "sequence_number": self._sequence,
                "time_utc": datetime.now(timezone.utc).isoformat(),
                "monotonic_elapsed_ms": round(
                    (time.monotonic() - self._started_monotonic) * 1000.0, 3
                ),
                "session_id": self.session_id,
                "application_version": self.app_version,
                "event": name,
            }
            for key, value in {
                "user_action": action,
                "software_request": request,
                "internal_state": state,
                "actual_result": result,
                "test_result": test_result,
            }.items():
                if value is not None:
                    record[key] = _json_safe(value)
            if details:
                record["details"] = _json_safe(details)
            if failure is not None:
                record["failure"] = _redact_text(str(failure))
                if isinstance(failure, BaseException):
                    record["failure_type"] = type(failure).__name__
                    record["traceback"] = _redact_text(
                        "".join(traceback.format_exception(failure))[-12000:]
                    )
                record["is_first_failure"] = not self._first_failure_written
                self._first_failure_written = True
            record = self._bound_record(record)
            serialized = _record_json(record) + "\n"
            try:
                current_bytes = self.path.stat().st_size
            except OSError:
                current_bytes = 0
            self._remember_record(record)
            if current_bytes + len(serialized.encode("utf-8")) > self.max_log_bytes:
                try:
                    self._compact_log_locked()
                except OSError:
                    # Keep the new evidence in memory and stop growing the file.
                    # A later event or support export can retry compaction.
                    pass
            else:
                try:
                    with self.path.open("a", encoding="utf-8") as handle:
                        handle.write(serialized)
                except OSError:
                    # Diagnostic I/O must never stop scanning. The bounded
                    # in-memory evidence remains available for this session.
                    pass
            return event_id

    def _bound_record(self, record: dict[str, Any]) -> dict[str, Any]:
        """Return a valid JSON record no larger than ``MAX_EVENT_BYTES``."""

        encoded = _record_json(record).encode("utf-8")
        if len(encoded) <= self.MAX_EVENT_BYTES:
            return record
        bounded = {
            key: value
            for key, value in record.items()
            if key not in {"details", "traceback"}
        }
        bounded["details"] = {
            "payload_omitted": "event exceeded diagnostic size limit",
            "original_size_bytes": len(encoded),
        }
        if "failure" in bounded:
            bounded["failure"] = str(bounded["failure"])[:4096]
        # Optional action/request/state/result fields can each be large. Fall
        # back to a deliberately small core envelope rather than letting their
        # combined size defeat the per-event limit.
        if len(_record_json(bounded).encode("utf-8")) > self.MAX_EVENT_BYTES:
            core_limits = {
                "event_id": 64,
                "time_utc": 64,
                "session_id": 64,
                "application_version": 64,
                "event": 256,
                "failure_type": 128,
            }
            minimal: dict[str, Any] = {}
            for key in (
                "event_id",
                "sequence_number",
                "time_utc",
                "monotonic_elapsed_ms",
                "session_id",
                "application_version",
                "event",
                "failure_type",
                "is_first_failure",
            ):
                if key not in bounded:
                    continue
                value = bounded[key]
                if key in core_limits:
                    value = str(value)[: core_limits[key]]
                minimal[key] = value
            minimal["details"] = {
                "payload_omitted": "event exceeded diagnostic size limit",
                "original_size_bytes": len(encoded),
            }
            bounded = minimal
        if len(_record_json(bounded).encode("utf-8")) > self.MAX_EVENT_BYTES:
            bounded = {
                "event": "diagnostic_event_omitted",
                "details": {"original_size_bytes": len(encoded)},
            }
        return bounded

    def _remember_record(self, record: dict[str, Any]) -> None:
        """Retain the evidence needed to compact a repetitive live session."""

        event_name = str(record.get("event", "unknown"))
        self._event_counts[event_name] += 1
        self._recent_events.append(record)
        if self._first_event is None:
            self._first_event = record
        if "failure" in record:
            self._failure_events.append(record)
            if self._first_failure is None:
                self._first_failure = record
        if event_name in self._latest_by_event:
            self._latest_by_event[event_name] = record
        elif len(self._latest_by_event) < self.MAX_TRACKED_EVENT_TYPES:
            self._latest_by_event[event_name] = record

    def _compact_log_locked(self) -> None:
        """Atomically replace an oversized log with bounded useful evidence.

        Exact recent records, the first failure, recent failures, and the latest
        record for every event type are prioritized. Counts retain the frequency
        of repetitive records such as per-frame scan telemetry.
        """

        self._compaction_count += 1
        self._sequence += 1
        summary = {
            "event_id": str(uuid.uuid4()),
            "sequence_number": self._sequence,
            "time_utc": datetime.now(timezone.utc).isoformat(),
            "monotonic_elapsed_ms": round(
                (time.monotonic() - self._started_monotonic) * 1000.0, 3
            ),
            "session_id": self.session_id,
            "application_version": self.app_version,
            "event": "diagnostic_log_compacted",
            "internal_state": "bounded",
            "actual_result": "ok",
            "details": {
                "compaction_count": self._compaction_count,
                "log_limit_bytes": self.max_log_bytes,
                "event_counts": dict(self._event_counts),
            },
        }
        summary = self._bound_record(summary)
        self._remember_record(summary)

        prioritized: list[dict[str, Any]] = []
        if self._first_event is not None:
            prioritized.append(self._first_event)
        if self._first_failure is not None:
            prioritized.append(self._first_failure)
        prioritized.extend(self._failure_events)
        prioritized.extend(self._latest_by_event.values())

        chosen: dict[str, dict[str, Any]] = {}
        used = 0
        reserve = len(_record_json(summary).encode("utf-8")) + 1
        budget = max(512, self._compact_target_bytes - reserve)

        def consider(record: dict[str, Any]) -> None:
            nonlocal used
            event_id = str(record.get("event_id", ""))
            if not event_id or event_id in chosen:
                return
            size = len(_record_json(record).encode("utf-8")) + 1
            if used + size <= budget:
                chosen[event_id] = record
                used += size

        for record in prioritized:
            consider(record)
        # Fill the remaining space with the newest exact records, then restore
        # chronological order for human and machine readers.
        for record in reversed(self._recent_events):
            consider(record)
        ordered = sorted(chosen.values(), key=lambda item: int(item["sequence_number"]))
        retained_original = sum(
            1 for item in ordered if item.get("event") != "diagnostic_log_compacted"
        )
        summary["details"].update(
            {
                "exact_records_retained": retained_original,
                "original_events_seen": sum(
                    count
                    for name, count in self._event_counts.items()
                    if name != "diagnostic_log_compacted"
                ),
            }
        )
        ordered = [
            item for item in ordered if item.get("event") != "diagnostic_log_compacted"
        ]
        ordered.append(summary)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".compact", dir=self.path.parent
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                for record in ordered:
                    handle.write(_record_json(record) + "\n")
            os.replace(temporary_name, self.path)
        except Exception:
            try:
                os.close(descriptor)
            except OSError:
                pass
            try:
                os.unlink(temporary_name)
            except OSError:
                pass
            raise

    def export_support_bundle(
        self,
        destination: Path,
        *,
        metadata: Mapping[str, Any] | None = None,
        attachments: Mapping[str, Path] | None = None,
    ) -> Path:
        """Create an atomic, uploadable ZIP for troubleshooting.

        The current session log and a small system manifest are always included.
        Camera images, point clouds, and calibration files are never collected
        implicitly; callers must pass each optional attachment deliberately.
        """

        output = Path(destination)
        if output.suffix.lower() != ".zip":
            output = output.with_suffix(".zip")
        output.parent.mkdir(parents=True, exist_ok=True)
        self.event(
            "support_bundle_export_requested",
            action="Export support bundle",
            request="Create diagnostic ZIP",
            state="collecting",
            destination_name=output.name,
        )

        included: list[tuple[str, Path, int]] = []
        skipped: list[dict[str, str]] = []
        total_attachment_bytes = 0
        for requested_name, requested_path in (attachments or {}).items():
            if len(included) >= self.MAX_ATTACHMENT_COUNT:
                skipped.append(
                    {"name": str(requested_name), "reason": "attachment count limit reached"}
                )
                continue
            try:
                archive_name = _safe_attachment_name(requested_name)
            except ValueError as error:
                skipped.append({"name": str(requested_name), "reason": str(error)})
                continue
            path = Path(requested_path)
            if not path.is_file():
                skipped.append({"name": archive_name, "reason": "file not found"})
                continue
            try:
                file_bytes = path.stat().st_size
            except OSError as error:
                skipped.append({"name": archive_name, "reason": str(error)})
                continue
            if file_bytes > self.MAX_ATTACHMENT_BYTES:
                skipped.append(
                    {
                        "name": archive_name,
                        "reason": f"file exceeds {self.MAX_ATTACHMENT_BYTES} byte limit",
                    }
                )
                continue
            if total_attachment_bytes + file_bytes > self.MAX_TOTAL_ATTACHMENT_BYTES:
                skipped.append(
                    {
                        "name": archive_name,
                        "reason": "total attachment byte limit reached",
                    }
                )
                continue
            included.append((archive_name, path, file_bytes))
            total_attachment_bytes += file_bytes

        manifest = {
            "schema": "laserline3d.support.v1",
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "session_id": self.session_id,
            "application_version": self.app_version,
            "diagnostic_log": self.path.name,
            "system": {
                "operating_system": platform.system(),
                "os_release": platform.release(),
                "machine": platform.machine(),
                "python": platform.python_version(),
                "packaged_application": bool(getattr(sys, "frozen", False)),
            },
            "metadata": _json_safe(dict(metadata or {})),
            "attachments": [name for name, _path, _size in included],
            "attachment_sizes_bytes": {
                name: size for name, _path, size in included
            },
            "skipped_attachments": skipped,
            "recent_event_count": 0,
            "limits": {
                "session_log_bytes": self.max_log_bytes,
                "attachment_count": self.MAX_ATTACHMENT_COUNT,
                "attachment_bytes_each": self.MAX_ATTACHMENT_BYTES,
                "attachment_bytes_total": self.MAX_TOTAL_ATTACHMENT_BYTES,
                "support_bundle_bytes": self.MAX_SUPPORT_BUNDLE_BYTES,
            },
            "privacy": (
                "No camera images or point clouds are included unless the user "
                "explicitly selected them as attachments. Review this ZIP before sharing."
            ),
        }

        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{output.name}.", suffix=".tmp", dir=output.parent
        )
        os.close(descriptor)
        try:
            # Snapshot under the same lock used by event writes so the embedded
            # JSONL can never end in a concurrently appended partial record.
            with self._lock:
                log_snapshot = self.path.read_bytes()
                manifest["recent_event_count"] = len(self._recent_events)
            with zipfile.ZipFile(
                temporary, "w", compression=zipfile.ZIP_DEFLATED
            ) as archive:
                archive.writestr(
                    "manifest.json",
                    json.dumps(manifest, indent=2, allow_nan=False) + "\n",
                )
                archive.writestr("diagnostics/current-session.jsonl", log_snapshot)
                for archive_name, path, expected_size in included:
                    payload = _read_bounded_file(
                        path, min(expected_size, self.MAX_ATTACHMENT_BYTES)
                    )
                    archive.writestr(f"attachments/{archive_name}", payload)
            if Path(temporary).stat().st_size > self.MAX_SUPPORT_BUNDLE_BYTES:
                raise ValueError(
                    "support bundle exceeded its safety limit; remove optional attachments"
                )
            os.replace(temporary, output)
            self.event(
                "support_bundle_exported",
                action="Export support bundle",
                state="ready_to_share",
                result="ok",
                destination_name=output.name,
                attachment_count=len(included),
            )
            return output
        except Exception as error:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            self.event("support_bundle_export_failed", failure=error)
            raise


def _json_safe(value: Any) -> Any:
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, Path):
        return _redact_text(str(value))
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Mapping):
        output: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= 256:
                output["_omitted_items"] = len(value) - 256
                break
            key_text = str(key)
            if _is_sensitive_field(key_text):
                output[key_text] = "[REDACTED]"
            else:
                output[key_text] = _json_safe(item)
        return output
    if isinstance(value, (list, tuple, set)):
        items = list(value)
        result = [_json_safe(v) for v in items[:256]]
        if len(items) > 256:
            result.append({"_omitted_items": len(items) - 256})
        return result
    if hasattr(value, "tolist"):
        return _json_safe(value.tolist())
    try:
        json.dumps(value, allow_nan=False)
        return value
    except TypeError:
        return _redact_text(repr(value))


def _redact_text(value: str) -> str:
    """Replace user/workspace prefixes while retaining useful relative context."""

    text = str(value)
    # Keep diagnostics useful without ever retaining common credential forms.
    text = re.sub(r"\bsk-[A-Za-z0-9_-]{12,}\b", "[REDACTED_API_KEY]", text)
    text = re.sub(
        r"\bgh[pousr]_[A-Za-z0-9_]{12,}\b", "[REDACTED_GITHUB_TOKEN]", text
    )
    text = re.sub(
        r"(?i)\b(bearer|password|passphrase|api[_-]?key|access[_-]?token)\s*[:=]\s*[^\s,;]+",
        lambda match: f"{match.group(1)}=[REDACTED]",
        text,
    )
    text = re.sub(
        r"(?i)\b(bearer)\s+[^\s,;]+",
        lambda match: f"{match.group(1)} [REDACTED]",
        text,
    )
    replacements: list[tuple[str, str]] = []
    try:
        replacements.append((str(Path.home()), "%USERPROFILE%"))
    except RuntimeError:
        pass
    try:
        replacements.append((str(Path.cwd()), "%WORKSPACE%"))
    except OSError:
        pass
    for original, replacement in sorted(
        replacements, key=lambda item: len(item[0]), reverse=True
    ):
        if original:
            text = re.sub(re.escape(original), replacement, text, flags=re.IGNORECASE)
            text = re.sub(
                re.escape(original.replace("\\", "/")),
                replacement,
                text,
                flags=re.IGNORECASE,
            )
    if len(text) > 16384:
        text = text[:16384] + "…[truncated]"
    return text


def _is_sensitive_field(name: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    exact = {
        "api_key",
        "apikey",
        "authorization",
        "clipboard",
        "clipboard_text",
        "cookie",
        "input_text",
        "password",
        "passphrase",
        "raw_text",
        "secret",
        "text",
        "token",
        "typed_text",
        "user_text",
    }
    return normalized in exact or normalized.endswith(
        ("_api_key", "_password", "_secret", "_token")
    )


def _record_json(record: Mapping[str, Any]) -> str:
    return json.dumps(record, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def _read_bounded_file(path: Path, maximum_bytes: int) -> bytes:
    """Read a stable, size-bounded attachment or reject a growing file."""

    with path.open("rb") as handle:
        payload = handle.read(maximum_bytes + 1)
    if len(payload) > maximum_bytes:
        raise ValueError(f"attachment grew beyond {maximum_bytes} byte limit")
    return payload


def frame_statistics(frame_bgr: Any) -> dict[str, Any]:
    """Return compact, privacy-safe measurements for a BGR camera frame.

    Only aggregate channel and image-quality scalars are returned. No pixels,
    thumbnails, histograms, hashes, filenames, or other reconstructable image
    content are retained.
    """

    image = np.asarray(frame_bgr)
    if image.ndim != 3 or image.shape[2] != 3:
        raise ValueError("frame must be a height x width x 3 BGR image")
    if image.shape[0] < 1 or image.shape[1] < 1:
        raise ValueError("frame must contain at least one pixel")
    if not np.issubdtype(image.dtype, np.number):
        raise TypeError("frame pixels must be numeric")
    if np.issubdtype(image.dtype, np.floating) and not np.all(np.isfinite(image)):
        raise ValueError("frame pixels must be finite")
    bgr = np.clip(image, 0, 255).astype(np.uint8, copy=False)
    source_height, source_width = bgr.shape[:2]
    source_pixels = source_height * source_width
    flat_bgr = bgr.reshape(-1, 3)
    if source_pixels > MAX_FRAME_STATISTICS_PIXELS:
        indices = np.linspace(
            0,
            source_pixels - 1,
            num=MAX_FRAME_STATISTICS_PIXELS,
            dtype=np.int64,
        )
        sample_bgr = flat_bgr[indices]
        spatial_scale = math.sqrt(MAX_FRAME_STATISTICS_PIXELS / source_pixels)
        sharpness_width = max(1, int(source_width * spatial_scale))
        sharpness_height = max(1, int(source_height * spatial_scale))
        while sharpness_width * sharpness_height > MAX_FRAME_STATISTICS_PIXELS:
            if sharpness_width >= sharpness_height and sharpness_width > 1:
                sharpness_width -= 1
            elif sharpness_height > 1:
                sharpness_height -= 1
        sharpness_bgr = cv2.resize(
            bgr,
            (sharpness_width, sharpness_height),
            interpolation=cv2.INTER_AREA,
        )
        sampling_method = "deterministic_evenly_spaced_source_pixels"
    else:
        sample_bgr = flat_bgr
        sharpness_bgr = bgr
        sharpness_width = source_width
        sharpness_height = source_height
        sampling_method = "all_source_pixels"
    sample_image = sample_bgr.reshape(-1, 1, 3)
    gray = cv2.cvtColor(sample_image, cv2.COLOR_BGR2GRAY).reshape(-1)
    hsv = cv2.cvtColor(sample_image, cv2.COLOR_BGR2HSV).reshape(-1, 3)
    sharpness_gray = cv2.cvtColor(sharpness_bgr, cv2.COLOR_BGR2GRAY)

    def channel(values: np.ndarray) -> dict[str, Any]:
        percentiles = np.percentile(values, [1, 5, 50, 95, 99])
        return {
            "mean": round(float(np.mean(values)), 4),
            "standard_deviation": round(float(np.std(values)), 4),
            "percentiles": {
                key: round(float(value), 4)
                for key, value in zip(
                    ("p01", "p05", "p50", "p95", "p99"), percentiles
                )
            },
        }

    gray_stats = channel(gray)
    gray_percentiles = gray_stats["percentiles"]
    return {
        "schema": "laserline3d.frame-statistics.v1",
        "dimensions": {
            "width": int(bgr.shape[1]),
            "height": int(bgr.shape[0]),
            "channels": 3,
        },
        "bgr": {
            "blue": channel(sample_bgr[:, 0]),
            "green": channel(sample_bgr[:, 1]),
            "red": channel(sample_bgr[:, 2]),
        },
        "gray": gray_stats,
        "hsv": {
            "hue_opencv_0_179": channel(hsv[:, 0]),
            "saturation": channel(hsv[:, 1]),
            "value": channel(hsv[:, 2]),
        },
        "clipping_percent": {
            "gray_near_black_le_5": round(float(np.mean(gray <= 5) * 100.0), 4),
            "gray_near_white_ge_250": round(float(np.mean(gray >= 250) * 100.0), 4),
            "any_channel_low_le_5": round(
                float(np.mean(np.any(sample_bgr <= 5, axis=1)) * 100.0), 4
            ),
            "any_channel_high_ge_250": round(
                float(np.mean(np.any(sample_bgr >= 250, axis=1)) * 100.0), 4
            ),
        },
        "contrast": {
            "gray_standard_deviation": gray_stats["standard_deviation"],
            "gray_p95_minus_p05": round(
                float(gray_percentiles["p95"] - gray_percentiles["p05"]), 4
            ),
        },
        "sharpness": {
            "laplacian_variance": round(
                float(cv2.Laplacian(sharpness_gray, cv2.CV_64F).var()), 4
            )
        },
        "sampling": {
            "method": sampling_method,
            "source_pixels": source_pixels,
            "sampled_pixels": int(len(sample_bgr)),
            "maximum_sample_pixels": MAX_FRAME_STATISTICS_PIXELS,
            "sampled_fraction": round(float(len(sample_bgr) / source_pixels), 6),
            "sharpness_dimensions": {
                "width": sharpness_width,
                "height": sharpness_height,
            },
        },
        "privacy": "aggregate measurements only; no image content retained",
    }


def _safe_attachment_name(value: str) -> str:
    """Return a flat, portable archive name or reject ambiguous paths."""

    name = str(value).strip().replace("\\", "/")
    if not name or name in {".", ".."} or "/" in name:
        raise ValueError("attachment name must be a single file name")
    return name


def install_exception_hook(diagnostics: DiagnosticLog) -> None:
    previous_thread_hook = threading.excepthook

    def hook(kind: type[BaseException], value: BaseException, tb: Any) -> None:
        diagnostics.event(
            "unhandled_exception",
            state="application_crash",
            result="failed",
            failure=value,
            thread="main",
        )
        logging.getLogger(__name__).critical(
            "Unhandled exception", exc_info=(kind, value, tb)
        )
        sys.__excepthook__(kind, value, tb)

    def thread_hook(args: threading.ExceptHookArgs) -> None:
        diagnostics.event(
            "unhandled_thread_exception",
            state="background_thread_crash",
            result="failed",
            failure=args.exc_value,
            thread=args.thread.name if args.thread is not None else "unknown",
        )
        previous_thread_hook(args)

    sys.excepthook = hook
    threading.excepthook = thread_hook
