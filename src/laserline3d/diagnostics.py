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
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


class DiagnosticLog:
    """Thread-safe, bounded JSONL action trace for one application session."""

    MAX_SESSION_LOGS = 20
    MAX_RECENT_EVENTS = 1000

    def __init__(
        self,
        directory: Path | None = None,
        *,
        app_version: str = "unknown",
    ) -> None:
        local_data = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
        root = directory or local_data / "LaserLine3D" / "diagnostics"
        root.mkdir(parents=True, exist_ok=True)
        self.session_id = str(uuid.uuid4())
        self.app_version = str(app_version)
        self._started_monotonic = time.monotonic()
        self._sequence = 0
        self._lock = threading.RLock()
        self._recent_events: deque[dict[str, Any]] = deque(
            maxlen=self.MAX_RECENT_EVENTS
        )
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
        """Keep diagnostic storage bounded while preserving recent sessions."""

        logs = sorted(
            root.glob("laserline3d_*.jsonl"),
            key=lambda path: path.stat().st_mtime,
        )
        remove_count = max(0, len(logs) - (self.MAX_SESSION_LOGS - 1))
        for old_log in logs[:remove_count]:
            try:
                old_log.unlink()
            except OSError:
                # Logging must never prevent the scanner from starting.
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
            self._recent_events.append(record)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n"
                )
            return event_id

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

        included: list[tuple[str, Path]] = []
        skipped: list[dict[str, str]] = []
        for requested_name, requested_path in (attachments or {}).items():
            try:
                archive_name = _safe_attachment_name(requested_name)
            except ValueError as error:
                skipped.append({"name": str(requested_name), "reason": str(error)})
                continue
            path = Path(requested_path)
            if not path.is_file():
                skipped.append({"name": archive_name, "reason": "file not found"})
                continue
            included.append((archive_name, path))

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
            "attachments": [name for name, _path in included],
            "skipped_attachments": skipped,
            "recent_event_count": 0,
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
                for archive_name, path in included:
                    archive.write(path, f"attachments/{archive_name}")
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
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
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
    return text


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
