"""Atomic, validated complete-test-run archives.

This deliberately does not share the compact support-bundle attachment path.
Callers enumerate every artifact explicitly; this module never scans a folder
and never moves or modifies a source artifact.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable, Mapping

from .diagnostics import sanitize_for_diagnostics


COMPLETE_RUN_SCHEMA = "laserline3d.complete-run.v2"
MAX_ARTIFACT_COUNT = 128
MAX_ARCHIVE_PATH_LENGTH = 240
MAX_DIAGNOSTICS_BYTES = 8 * 1024 * 1024
MAX_TOTAL_SOURCE_BYTES = 8 * 1024 * 1024 * 1024
STREAM_CHUNK_BYTES = 1024 * 1024
MIN_FREE_SPACE_MARGIN_BYTES = 64 * 1024 * 1024

ProgressCallback = Callable[[str, int, int], None]
CancelCheck = Callable[[], bool]

_RESERVED_PATHS = {
    "manifest.json",
    "readme.txt",
    "diagnostics/events.jsonl",
    "run/summary.json",
    "run/settings.json",
}
_VALID_RUN_STATUSES = {"active", "completed", "partial", "failed", "cancelled"}
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


@dataclass(frozen=True, slots=True)
class ArtifactRelationship:
    """Machine-readable relationship to another archive artifact."""

    kind: str
    target: str


@dataclass(frozen=True, slots=True)
class RunBundleArtifact:
    """One explicitly selected source file for a complete-run ZIP.

    ``source_path=None`` records an expected but unavailable output. Camera or
    background image roles/paths are treated as private automatically; callers
    can also set ``requires_image_opt_in=True``. They are omitted unless the
    caller passes ``include_private_images=True``.
    """

    archive_path: str
    source_path: Path | None
    role: str
    stage: str
    relationship: ArtifactRelationship | None = None
    required: bool = True
    requires_image_opt_in: bool = False
    missing_reason: str | None = None


class RunBundleCancelledError(RuntimeError):
    """Raised when a caller cancels archive creation before publication."""


def filter_run_diagnostics_jsonl(payload: bytes, test_run_id: str) -> bytes:
    """Validate, sanitize, and retain only records for ``test_run_id``.

    The input may be a run snapshot or a bounded application-session JSONL.
    Invalid JSON is rejected instead of silently producing misleading evidence.
    """

    run_id = _safe_identifier(test_run_id, "test_run_id")
    raw = bytes(payload)
    if len(raw) > MAX_DIAGNOSTICS_BYTES:
        raise ValueError(
            f"run diagnostics exceed the {MAX_DIAGNOSTICS_BYTES} byte safety limit"
        )
    selected: list[bytes] = []
    for line_number, line in enumerate(raw.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError(
                f"run diagnostics contain invalid JSON on line {line_number}"
            ) from error
        if not isinstance(record, Mapping):
            raise ValueError(
                f"run diagnostics line {line_number} is not a JSON object"
            )
        if str(record.get("test_run_id", "")) != run_id:
            continue
        sanitized = sanitize_for_diagnostics(dict(record))
        selected.append(_json_bytes(sanitized, compact=True))
    if not selected:
        raise ValueError("run diagnostics contain no events for this test_run_id")
    result = b"".join(selected)
    if len(result) > MAX_DIAGNOSTICS_BYTES:
        raise ValueError(
            f"filtered run diagnostics exceed the {MAX_DIAGNOSTICS_BYTES} byte safety limit"
        )
    return result


def create_complete_run_bundle(
    destination: Path,
    *,
    application_session_id: str,
    test_run_id: str,
    application_version: str,
    diagnostics_jsonl: bytes,
    artifacts: Iterable[RunBundleArtifact],
    scan_operation_id: str | None = None,
    run_summary: Mapping[str, Any] | None = None,
    settings: Mapping[str, Any] | None = None,
    run_started_utc: str | None = None,
    run_finished_utc: str | None = None,
    run_status: str = "completed",
    include_private_images: bool = False,
    progress_callback: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
) -> Path:
    """Stream an explicit run artifact set into an atomic, validated ZIP.

    Large models bypass the compact support bundle's attachment limits. The
    archive is written beside the destination, validated by CRC, size, SHA-256,
    identity, and manifest content, and only then atomically replaces the
    destination. A failed attempt leaves an existing destination untouched.
    """

    session_id = _safe_identifier(application_session_id, "application_session_id")
    run_id = _safe_identifier(test_run_id, "test_run_id")
    operation_id = (
        _safe_identifier(scan_operation_id, "scan_operation_id")
        if scan_operation_id is not None
        else None
    )
    normalized_status = str(run_status).strip().lower()
    if normalized_status not in _VALID_RUN_STATUSES:
        raise ValueError("invalid run_status")
    version = str(application_version).strip()[:128]
    if not version:
        raise ValueError("application_version must not be empty")

    requested_artifacts = list(artifacts)
    if len(requested_artifacts) > MAX_ARTIFACT_COUNT:
        raise ValueError(f"artifact count exceeds the {MAX_ARTIFACT_COUNT} item limit")
    prepared, total_source_bytes = _prepare_artifacts(
        requested_artifacts,
        include_private_images=include_private_images,
    )
    if total_source_bytes > MAX_TOTAL_SOURCE_BYTES:
        raise ValueError(
            f"selected artifacts exceed the {MAX_TOTAL_SOURCE_BYTES} byte safety limit"
        )

    filtered_diagnostics = filter_run_diagnostics_jsonl(diagnostics_jsonl, run_id)
    safe_summary = sanitize_for_diagnostics(dict(run_summary or {}))
    safe_settings = sanitize_for_diagnostics(dict(settings or {}))
    generated_payloads = [
        (
            "README.txt",
            _readme_bytes(include_private_images=include_private_images),
            "documentation",
            "run",
        ),
        ("diagnostics/events.jsonl", filtered_diagnostics, "diagnostics", "run"),
        ("run/summary.json", _json_bytes(safe_summary), "run_summary", "run"),
        ("run/settings.json", _json_bytes(safe_settings), "settings", "run"),
    ]

    output = Path(destination)
    if output.suffix.lower() != ".zip":
        output = output.with_suffix(".zip")
    output_identity = os.path.normcase(str(output.resolve(strict=False)))
    for item in prepared:
        if item.source_path is None:
            continue
        source_identity = os.path.normcase(str(item.source_path.resolve(strict=False)))
        if source_identity == output_identity:
            raise ValueError("bundle destination cannot also be a source artifact")
    output.parent.mkdir(parents=True, exist_ok=True)
    required_free_bytes = (
        total_source_bytes
        + sum(len(payload) for _path, payload, _role, _stage in generated_payloads)
        + MIN_FREE_SPACE_MARGIN_BYTES
    )
    available_free_bytes = shutil.disk_usage(output.parent).free
    if available_free_bytes < required_free_bytes:
        raise OSError(
            "not enough free space beside the selected ZIP destination "
            f"(need at least {required_free_bytes:,} bytes; "
            f"{available_free_bytes:,} bytes available)"
        )
    _report_progress(
        progress_callback,
        cancel_check,
        "Preparing archive",
        0,
        total_source_bytes,
    )
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent
    )
    temporary = Path(temporary_name)
    try:
        manifest_items: list[dict[str, Any]] = []
        with os.fdopen(descriptor, "w+b") as output_stream:
            with zipfile.ZipFile(
                output_stream,
                mode="w",
                compression=zipfile.ZIP_DEFLATED,
                allowZip64=True,
            ) as archive:
                for archive_path, payload, role, stage in generated_payloads:
                    size, digest = _write_bytes_entry(
                        archive,
                        archive_path,
                        payload,
                        progress_callback=progress_callback,
                        cancel_check=cancel_check,
                    )
                    manifest_items.append(
                        _manifest_item(
                            archive_path=archive_path,
                            role=role,
                            stage=stage,
                            status="included",
                            required=True,
                            size=size,
                            digest=digest,
                        )
                    )
                for item in prepared:
                    artifact = item.artifact
                    if item.status != "included":
                        manifest_items.append(
                            _manifest_item(
                                archive_path=item.archive_path,
                                role=artifact.role,
                                stage=artifact.stage,
                                status=item.status,
                                required=_artifact_required(artifact, item.archive_path),
                                size=None,
                                digest=None,
                                relationship=artifact.relationship,
                                reason=item.reason,
                            )
                        )
                        continue
                    if item.source_path is None or item.stat_result is None:
                        raise RuntimeError("included artifact was not prepared")
                    size, digest = _stream_file_entry(
                        archive,
                        item.archive_path,
                        item.source_path,
                        item.stat_result,
                        progress_callback=progress_callback,
                        cancel_check=cancel_check,
                    )
                    manifest_items.append(
                        _manifest_item(
                            archive_path=item.archive_path,
                            role=artifact.role,
                            stage=artifact.stage,
                            status="included",
                            required=_artifact_required(artifact, item.archive_path),
                            size=size,
                            digest=digest,
                            relationship=artifact.relationship,
                        )
                    )

                missing_required = any(
                    entry["required"] and entry["status"] != "included"
                    for entry in manifest_items
                )
                package_status = "partial" if missing_required else "complete"
                manifest = {
                    "schema": COMPLETE_RUN_SCHEMA,
                    "created_utc": datetime.now(timezone.utc).isoformat(),
                    "application_version": version,
                    "application_session_id": session_id,
                    "test_run_id": run_id,
                    "scan_operation_id": operation_id,
                    "run_started_utc": _safe_optional_timestamp(run_started_utc),
                    "run_finished_utc": _safe_optional_timestamp(run_finished_utc),
                    "run_status": normalized_status,
                    "package_status": package_status,
                    "items": manifest_items,
                    "item_counts": {
                        status: sum(
                            item["status"] == status for item in manifest_items
                        )
                        for status in ("included", "missing", "omitted")
                    },
                    "limits": {
                        "artifact_count": MAX_ARTIFACT_COUNT,
                        "diagnostics_bytes": MAX_DIAGNOSTICS_BYTES,
                        "total_source_bytes": MAX_TOTAL_SOURCE_BYTES,
                    },
                    "privacy": {
                        "camera_background_images_requested": bool(
                            include_private_images
                        ),
                        "source_paths_in_manifest": False,
                        "artifact_selection": "explicit_only_no_directory_scanning",
                    },
                    "integrity": {
                        "algorithm": "SHA-256",
                        "zip_crc_validated_before_publish": True,
                        "manifest_self_hash": "excluded_to_avoid_circular_content",
                    },
                }
                archive.writestr(
                    "manifest.json",
                    _json_bytes(manifest),
                    compress_type=zipfile.ZIP_DEFLATED,
                )
            output_stream.flush()
            os.fsync(output_stream.fileno())

        _validate_complete_run_bundle(
            temporary,
            expected_session_id=session_id,
            expected_run_id=run_id,
            expected_items=manifest_items,
            progress_callback=progress_callback,
            cancel_check=cancel_check,
        )
        _report_progress(
            progress_callback,
            cancel_check,
            "Publishing archive",
            1,
            1,
        )
        os.replace(temporary, output)
        return output
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        try:
            temporary.unlink()
        except OSError:
            pass
        raise


@dataclass(frozen=True, slots=True)
class _PreparedArtifact:
    artifact: RunBundleArtifact
    archive_path: str
    source_path: Path | None
    stat_result: os.stat_result | None
    status: str
    reason: str | None


def _prepare_artifacts(
    artifacts: list[RunBundleArtifact],
    *,
    include_private_images: bool,
) -> tuple[list[_PreparedArtifact], int]:
    prepared: list[_PreparedArtifact] = []
    names = {path.casefold() for path in _RESERVED_PATHS}
    total_source_bytes = 0
    for artifact in artifacts:
        archive_path = _safe_archive_path(artifact.archive_path)
        folded = archive_path.casefold()
        if folded in names:
            raise ValueError(f"duplicate or reserved archive path: {archive_path}")
        names.add(folded)
        _safe_manifest_label(artifact.role, "role")
        _safe_manifest_label(artifact.stage, "stage")
        if artifact.relationship is not None:
            _safe_manifest_label(artifact.relationship.kind, "relationship kind")
            _safe_archive_path(artifact.relationship.target)
        if _requires_image_opt_in(artifact, archive_path) and not include_private_images:
            prepared.append(
                _PreparedArtifact(
                    artifact,
                    archive_path,
                    None,
                    None,
                    "omitted",
                    "user_not_opted_in_to_camera_or_background_images",
                )
            )
            continue
        if artifact.source_path is None:
            reason = _safe_reason(artifact.missing_reason or "not_available")
            prepared.append(
                _PreparedArtifact(
                    artifact, archive_path, None, None, "missing", reason
                )
            )
            continue
        source = Path(artifact.source_path)
        try:
            stat_result = source.stat()
        except OSError as error:
            prepared.append(
                _PreparedArtifact(
                    artifact,
                    archive_path,
                    None,
                    None,
                    "missing",
                    (
                        "file_not_found"
                        if isinstance(error, FileNotFoundError)
                        else _safe_reason(f"source_unreadable_{type(error).__name__}")
                    ),
                )
            )
            continue
        if not source.is_file():
            prepared.append(
                _PreparedArtifact(
                    artifact,
                    archive_path,
                    None,
                    None,
                    "missing",
                    "not_a_regular_file",
                )
            )
            continue
        total_source_bytes += int(stat_result.st_size)
        prepared.append(
            _PreparedArtifact(
                artifact,
                archive_path,
                source,
                stat_result,
                "included",
                None,
            )
        )
    return prepared, total_source_bytes


def _stream_file_entry(
    archive: zipfile.ZipFile,
    archive_path: str,
    source_path: Path,
    expected_stat: os.stat_result,
    *,
    progress_callback: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
) -> tuple[int, str]:
    digest = hashlib.sha256()
    byte_count = 0
    with source_path.open("rb") as source, archive.open(
        archive_path, "w", force_zip64=True
    ) as destination:
        while True:
            chunk = source.read(STREAM_CHUNK_BYTES)
            if not chunk:
                break
            destination.write(chunk)
            digest.update(chunk)
            byte_count += len(chunk)
            _report_progress(
                progress_callback,
                cancel_check,
                f"Writing {archive_path}",
                byte_count,
                int(expected_stat.st_size),
            )
    current_stat = source_path.stat()
    if (
        byte_count != int(expected_stat.st_size)
        or int(current_stat.st_size) != int(expected_stat.st_size)
        or int(current_stat.st_mtime_ns) != int(expected_stat.st_mtime_ns)
    ):
        raise RuntimeError("an artifact changed while the run bundle was being created")
    return byte_count, digest.hexdigest()


def _write_bytes_entry(
    archive: zipfile.ZipFile,
    archive_path: str,
    payload: bytes,
    *,
    progress_callback: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
) -> tuple[int, str]:
    digest = hashlib.sha256()
    byte_count = 0
    with archive.open(archive_path, "w", force_zip64=True) as destination:
        for offset in range(0, len(payload), STREAM_CHUNK_BYTES):
            chunk = payload[offset : offset + STREAM_CHUNK_BYTES]
            destination.write(chunk)
            digest.update(chunk)
            byte_count += len(chunk)
            _report_progress(
                progress_callback,
                cancel_check,
                f"Writing {archive_path}",
                byte_count,
                len(payload),
            )
    return byte_count, digest.hexdigest()


def _manifest_item(
    *,
    archive_path: str,
    role: str,
    stage: str,
    status: str,
    required: bool,
    size: int | None,
    digest: str | None,
    relationship: ArtifactRelationship | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    relationship_payload = None
    if relationship is not None:
        relationship_payload = {
            "kind": _safe_manifest_label(relationship.kind, "relationship kind"),
            "target": _safe_archive_path(relationship.target),
        }
    return {
        "archive_path": archive_path,
        "role": _safe_manifest_label(role, "role"),
        "stage": _safe_manifest_label(stage, "stage"),
        "status": status,
        "required": bool(required),
        "size_bytes": size,
        "sha256": digest,
        "relationship": relationship_payload,
        "reason": reason,
    }


def _validate_complete_run_bundle(
    path: Path,
    *,
    expected_session_id: str,
    expected_run_id: str,
    expected_items: list[dict[str, Any]],
    progress_callback: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
) -> None:
    expected_included = {
        item["archive_path"]: item
        for item in expected_items
        if item["status"] == "included"
    }
    with zipfile.ZipFile(path, "r") as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("complete-run ZIP contains duplicate archive paths")
        if set(names) != set(expected_included) | {"manifest.json"}:
            raise ValueError("complete-run ZIP contents do not match its explicit plan")
        manifest = json.loads(archive.read("manifest.json"))
        if manifest.get("schema") != COMPLETE_RUN_SCHEMA:
            raise ValueError("complete-run manifest schema validation failed")
        if manifest.get("application_session_id") != expected_session_id:
            raise ValueError("complete-run application session identity changed")
        if manifest.get("test_run_id") != expected_run_id:
            raise ValueError("complete-run test identity changed")
        if manifest.get("items") != expected_items:
            raise ValueError("complete-run manifest item list changed")
        for archive_path, item in expected_included.items():
            digest = hashlib.sha256()
            byte_count = 0
            with archive.open(archive_path, "r") as source:
                while True:
                    chunk = source.read(STREAM_CHUNK_BYTES)
                    if not chunk:
                        break
                    digest.update(chunk)
                    byte_count += len(chunk)
                    _report_progress(
                        progress_callback,
                        cancel_check,
                        f"Validating {archive_path}",
                        byte_count,
                        int(item["size_bytes"]),
                    )
            if byte_count != item["size_bytes"]:
                raise ValueError(f"size validation failed for {archive_path}")
            if digest.hexdigest() != item["sha256"]:
                raise ValueError(f"SHA-256 validation failed for {archive_path}")


def _report_progress(
    callback: ProgressCallback | None,
    cancel_check: CancelCheck | None,
    phase: str,
    completed_bytes: int,
    total_bytes: int,
) -> None:
    if cancel_check is not None and cancel_check():
        raise RunBundleCancelledError("complete-run ZIP creation was cancelled")
    if callback is not None:
        callback(str(phase), int(completed_bytes), int(total_bytes))
    if cancel_check is not None and cancel_check():
        raise RunBundleCancelledError("complete-run ZIP creation was cancelled")


def _safe_archive_path(value: str) -> str:
    text = str(value).strip().replace("\\", "/")
    if (
        not text
        or len(text) > MAX_ARCHIVE_PATH_LENGTH
        or "\0" in text
        or any(ord(character) < 32 for character in text)
    ):
        raise ValueError("archive path is empty, too long, or invalid")
    if text.startswith("/") or re.match(r"^[A-Za-z]:", text):
        raise ValueError("archive path must be relative")
    raw_parts = text.split("/")
    if any(part in {"", ".", ".."} for part in raw_parts):
        raise ValueError("archive path contains an unsafe segment")
    for part in raw_parts:
        if (
            part.endswith((".", " "))
            or any(character in '<>:"|?*' for character in part)
            or part.split(".", 1)[0].upper() in _WINDOWS_RESERVED_NAMES
        ):
            raise ValueError("archive path is not portable to Windows")
    path = PurePosixPath(text)
    normalized = path.as_posix()
    if normalized.endswith("/"):
        raise ValueError("archive path must name a file")
    return normalized


def _requires_image_opt_in(
    artifact: RunBundleArtifact, archive_path: str
) -> bool:
    role = str(artifact.role).casefold()
    return bool(
        artifact.requires_image_opt_in
        or "image" in role
        or archive_path.casefold().startswith("images/")
    )


def _artifact_required(artifact: RunBundleArtifact, archive_path: str) -> bool:
    # Camera/background images are always optional evidence. Requiring an image
    # that the user declined would turn a privacy choice into a false failure.
    return bool(
        artifact.required and not _requires_image_opt_in(artifact, archive_path)
    )


def _safe_identifier(value: str, field: str) -> str:
    text = str(value).strip()
    if not _SAFE_ID.fullmatch(text):
        raise ValueError(f"{field} is empty or contains unsafe characters")
    return text


def _safe_manifest_label(value: str, field: str) -> str:
    text = str(value).strip()
    if not text or len(text) > 128 or any(ord(character) < 32 for character in text):
        raise ValueError(f"{field} is empty, too long, or invalid")
    return text


def _safe_reason(value: str) -> str:
    safe = sanitize_for_diagnostics(str(value))
    return str(safe)[:256]


def _safe_optional_timestamp(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or len(text) > 64 or any(ord(character) < 32 for character in text):
        raise ValueError("run timestamp is invalid")
    return text


def _json_bytes(value: Any, *, compact: bool = False) -> bytes:
    if compact:
        text = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
    else:
        text = json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2)
    return (text + "\n").encode("utf-8")


def _readme_bytes(*, include_private_images: bool) -> bytes:
    image_note = (
        "Camera/background images were eligible for inclusion because the user opted in."
        if include_private_images
        else "Camera/background images were excluded unless individually listed as omitted."
    )
    return (
        "LaserLine3D complete test-run evidence package\n\n"
        "This ZIP contains only explicitly selected artifacts. It does not scan source "
        "folders, and original files were copied without modification. See manifest.json "
        "for status, size, SHA-256, stage, role, and relationships.\n\n"
        f"{image_note}\n"
    ).encode("utf-8")
