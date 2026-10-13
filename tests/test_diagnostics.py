import json
import zipfile
from pathlib import Path

from laserline3d.diagnostics import DiagnosticLog


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
