import json
import zipfile
from pathlib import Path

import numpy as np

from laserline3d.diagnostics import (
    MAX_FRAME_STATISTICS_PIXELS,
    DiagnosticLog,
    frame_statistics,
)


def test_support_bundle_contains_current_log_manifest_and_opt_in_attachment(
    tmp_path: Path,
) -> None:
    diagnostics = DiagnosticLog(tmp_path / "logs", app_version="test-version")
    diagnostics.event(
        "slider_changed",
        red=127,
        dominance=44,
        difference=51,
        unsupported_property=float("nan"),
    )
    attachment = tmp_path / "camera-summary.json"
    attachment.write_text('{"camera": "test"}\n', encoding="utf-8")

    bundle = diagnostics.export_support_bundle(
        tmp_path / "share-me",
        metadata={"laser_settings": {"minimum_red": 127}},
        attachments={"camera-summary.json": attachment},
    )

    assert bundle.suffix == ".zip"
    with zipfile.ZipFile(bundle) as archive:
        assert set(archive.namelist()) == {
            "manifest.json",
            "diagnostics/current-session.jsonl",
            "attachments/camera-summary.json",
        }
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["schema"] == "laserline3d.support.v1"
        assert manifest["session_id"] == diagnostics.session_id
        assert manifest["application_version"] == "test-version"
        assert manifest["metadata"]["laser_settings"]["minimum_red"] == 127
        assert "camera images" in manifest["privacy"].lower()
        log = archive.read("diagnostics/current-session.jsonl").decode("utf-8")
        assert "slider_changed" in log
        assert "support_bundle_export_requested" in log
        records = [json.loads(line) for line in log.splitlines()]
        assert [record["sequence_number"] for record in records] == list(
            range(1, len(records) + 1)
        )
        assert all(record["event_id"] for record in records)
        assert all(record["application_version"] == "test-version" for record in records)
        slider = next(record for record in records if record["event"] == "slider_changed")
        assert slider["details"]["unsupported_property"] is None


def test_support_bundle_rejects_attachment_paths_and_does_not_leak_log_path(
    tmp_path: Path,
) -> None:
    diagnostics = DiagnosticLog(tmp_path / "private" / "logs")
    private_path = Path.home() / "private-user-folder" / "camera.json"
    diagnostics.event("private_path_example", path=str(private_path))
    bundle = diagnostics.export_support_bundle(
        tmp_path / "support.zip",
        attachments={"../private.json": tmp_path / "missing.json"},
    )

    with zipfile.ZipFile(bundle) as archive:
        manifest_text = archive.read("manifest.json").decode("utf-8")
        manifest = json.loads(manifest_text)
        assert manifest["attachments"] == []
        assert manifest["skipped_attachments"]
        assert str(tmp_path) not in manifest_text
        log_text = archive.read("diagnostics/current-session.jsonl").decode("utf-8")
        assert str(Path.home()) not in log_text
        assert "%USERPROFILE%" in log_text


def test_support_bundle_normalizes_non_finite_metadata_to_standard_json(
    tmp_path: Path,
) -> None:
    diagnostics = DiagnosticLog(tmp_path / "logs")
    bundle = diagnostics.export_support_bundle(
        tmp_path / "finite.zip",
        metadata={"nan": float("nan"), "positive_infinity": float("inf")},
    )

    with zipfile.ZipFile(bundle) as archive:
        manifest_text = archive.read("manifest.json").decode("utf-8")
        manifest = json.loads(manifest_text)
        assert manifest["metadata"]["nan"] is None
        assert manifest["metadata"]["positive_infinity"] is None
        assert "NaN" not in manifest_text
        assert "Infinity" not in manifest_text


def test_frame_statistics_are_aggregate_and_measure_brightness_and_detail() -> None:
    frame = np.zeros((8, 10, 3), dtype=np.uint8)
    frame[:, :5] = (10, 20, 30)
    frame[:, 5:] = (240, 250, 255)

    statistics = frame_statistics(frame)

    assert statistics["schema"] == "laserline3d.frame-statistics.v1"
    assert statistics["dimensions"] == {"width": 10, "height": 8, "channels": 3}
    assert statistics["bgr"]["red"]["percentiles"]["p50"] == 142.5
    assert statistics["gray"]["percentiles"]["p05"] < 30
    assert statistics["gray"]["percentiles"]["p95"] > 240
    assert statistics["contrast"]["gray_p95_minus_p05"] > 200
    assert statistics["sharpness"]["laplacian_variance"] > 0
    assert statistics["sampling"]["method"] == "all_source_pixels"
    assert statistics["sampling"]["sampled_pixels"] == 80
    assert "aggregate measurements" in statistics["privacy"]
    serialized = json.dumps(statistics)
    assert "pixel_values" not in serialized
    assert "histogram" not in serialized


def test_frame_statistics_reject_non_bgr_input() -> None:
    try:
        frame_statistics(np.zeros((8, 10), dtype=np.uint8))
    except ValueError as error:
        assert "BGR" in str(error)
    else:
        raise AssertionError("grayscale input must be rejected")


def test_frame_statistics_use_a_deterministic_bounded_large_frame_sample() -> None:
    rows = np.arange(500, dtype=np.uint16)[:, None]
    columns = np.arange(500, dtype=np.uint16)[None, :]
    frame = np.empty((500, 500, 3), dtype=np.uint8)
    frame[:, :, 0] = (rows % 256).astype(np.uint8)
    frame[:, :, 1] = (columns % 256).astype(np.uint8)
    frame[:, :, 2] = ((rows + columns) % 256).astype(np.uint8)

    first = frame_statistics(frame)
    second = frame_statistics(frame)

    assert first == second
    assert first["sampling"]["method"] == "deterministic_evenly_spaced_source_pixels"
    assert first["sampling"]["source_pixels"] == 250_000
    assert first["sampling"]["sampled_pixels"] == MAX_FRAME_STATISTICS_PIXELS
    sharpness_size = first["sampling"]["sharpness_dimensions"]
    assert sharpness_size["width"] * sharpness_size["height"] <= MAX_FRAME_STATISTICS_PIXELS


def test_active_log_compacts_and_preserves_failure_latest_types_and_counts(
    tmp_path: Path,
) -> None:
    diagnostics = DiagnosticLog(
        tmp_path / "logs", app_version="bounded", max_log_bytes=4096
    )
    diagnostics.event("camera_properties_reported", exposure=-6.0)
    diagnostics.event("first_problem", failure="triangulation unavailable")
    for index in range(300):
        diagnostics.event("scan_frame_processed", frame=index, payload="x" * 100)

    assert diagnostics.path.stat().st_size <= diagnostics.max_log_bytes
    records = [
        json.loads(line)
        for line in diagnostics.path.read_text(encoding="utf-8").splitlines()
    ]
    events = {record["event"] for record in records}
    assert "application_started" in events
    assert "camera_properties_reported" in events
    assert "first_problem" in events
    assert "diagnostic_log_compacted" in events
    summary = [
        record for record in records if record["event"] == "diagnostic_log_compacted"
    ][-1]
    assert summary["details"]["event_counts"]["scan_frame_processed"] >= 1
    exact_after_summary = sum(
        record["event"] == "scan_frame_processed"
        and record["sequence_number"] > summary["sequence_number"]
        for record in records
    )
    assert (
        summary["details"]["event_counts"]["scan_frame_processed"]
        + exact_after_summary
        == 300
    )


def test_diagnostics_redact_secrets_and_typed_text(tmp_path: Path) -> None:
    diagnostics = DiagnosticLog(tmp_path / "logs")
    diagnostics.event(
        "keyboard_activity",
        key="A",
        typed_text="private sentence",
        password="do-not-store",
        token="ghp_1234567890abcdefghijklmnop",
        api_key="provider-key-that-must-not-persist",
        apikey="second-provider-key-that-must-not-persist",
        note="Bearer hidden-credential-value",
    )
    text = diagnostics.path.read_text(encoding="utf-8")

    assert "private sentence" not in text
    assert "do-not-store" not in text
    assert "1234567890abcdefghijklmnop" not in text
    assert "provider-key-that-must-not-persist" not in text
    assert "second-provider-key-that-must-not-persist" not in text
    assert "hidden-credential-value" not in text
    assert text.count("[REDACTED]") >= 5
    assert '"key":"A"' in text


def test_diagnostic_event_hard_limit_uses_minimal_core_envelope(tmp_path: Path) -> None:
    diagnostics = DiagnosticLog(tmp_path / "logs")
    large = "x" * 20_000

    diagnostics.event(
        "oversized_event",
        action=large,
        request=large,
        state=large,
        result=large,
        test_result=large,
        extra=large,
    )

    serialized = diagnostics.path.read_text(encoding="utf-8").splitlines()[-1]
    record = json.loads(serialized)
    assert len(serialized.encode("utf-8")) <= diagnostics.MAX_EVENT_BYTES
    assert record["event"] == "oversized_event"
    assert record["details"]["payload_omitted"]
    assert record["details"]["original_size_bytes"] > diagnostics.MAX_EVENT_BYTES
    assert "user_action" not in record
    assert "software_request" not in record


def test_support_bundle_skips_oversized_attachment(
    tmp_path: Path, monkeypatch: object
) -> None:
    monkeypatch.setattr(DiagnosticLog, "MAX_ATTACHMENT_BYTES", 32)  # type: ignore[attr-defined]
    diagnostics = DiagnosticLog(tmp_path / "logs")
    oversized = tmp_path / "oversized.bin"
    oversized.write_bytes(b"x" * 33)

    bundle = diagnostics.export_support_bundle(
        tmp_path / "bounded.zip", attachments={"oversized.bin": oversized}
    )

    with zipfile.ZipFile(bundle) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["attachments"] == []
        assert "exceeds" in manifest["skipped_attachments"][0]["reason"]
        assert "attachments/oversized.bin" not in archive.namelist()
