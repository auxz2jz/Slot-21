import hashlib
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

import laserline3d.run_bundle as run_bundle
from laserline3d.diagnostics import DiagnosticLog
from laserline3d.run_bundle import (
    ArtifactRelationship,
    RunBundleArtifact,
    RunBundleCancelledError,
    create_complete_run_bundle,
)


def _finished_run(
    diagnostics: DiagnosticLog, event_name: str = "scan_finished"
) -> tuple[str, bytes]:
    run_id = diagnostics.start_test_run()
    diagnostics.event(event_name, result="ok", operation_id="scan-1")
    diagnostics.finish_test_run(summary={"accepted_frames": 12})
    return run_id, diagnostics.test_run_snapshot(run_id)


def _write(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def test_complete_run_bundle_contains_all_model_formats_sidecars_and_project(
    tmp_path: Path,
) -> None:
    diagnostics = DiagnosticLog(tmp_path / "logs", app_version="0.4-test")
    run_id, run_jsonl = _finished_run(diagnostics)
    sources = tmp_path / "private-source-folder"
    artifacts: list[RunBundleArtifact] = []
    expected_payloads: dict[str, bytes] = {}
    for suffix in ("ply", "obj", "stl"):
        model_payload = f"model-{suffix}\n".encode()
        sidecar_payload = json.dumps({"format": suffix}).encode()
        model_path = _write(sources / f"scan.{suffix}", model_payload)
        sidecar_path = _write(sources / f"scan.{suffix}.json", sidecar_payload)
        archive_model = f"models/final/scan.{suffix}"
        archive_sidecar = f"models/final/scan.{suffix}.json"
        expected_payloads[archive_model] = model_payload
        expected_payloads[archive_sidecar] = sidecar_payload
        artifacts.extend(
            [
                RunBundleArtifact(
                    archive_model,
                    model_path,
                    role="point_cloud" if suffix == "ply" else "surface_mesh",
                    stage="final",
                ),
                RunBundleArtifact(
                    archive_sidecar,
                    sidecar_path,
                    role="export_sidecar",
                    stage="final",
                    relationship=ArtifactRelationship("sidecar_for", archive_model),
                ),
            ]
        )
    project_payload = b"portable-project"
    project_path = _write(sources / "scan.llscan", project_payload)
    _write(sources / "not-selected-private-note.txt", b"must not be discovered")
    expected_payloads["project/final.llscan"] = project_payload
    artifacts.append(
        RunBundleArtifact(
            "project/final.llscan", project_path, role="project", stage="final"
        )
    )

    bundle = create_complete_run_bundle(
        tmp_path / "complete-test-run",
        application_session_id=diagnostics.session_id,
        test_run_id=run_id,
        scan_operation_id="scan-1",
        application_version="0.4-test",
        diagnostics_jsonl=run_jsonl,
        artifacts=artifacts,
        run_summary=diagnostics.test_run_metadata(run_id),
        settings={"laser": {"minimum_red": 127}, "bad_number": float("nan")},
        run_status="completed",
    )

    assert bundle.suffix == ".zip"
    with zipfile.ZipFile(bundle) as archive:
        assert archive.testzip() is None
        manifest_text = archive.read("manifest.json").decode("utf-8")
        manifest = json.loads(manifest_text)
        assert manifest["schema"] == "laserline3d.complete-run.v2"
        assert manifest["application_session_id"] == diagnostics.session_id
        assert manifest["test_run_id"] == run_id
        assert manifest["scan_operation_id"] == "scan-1"
        assert manifest["package_status"] == "complete"
        assert manifest["privacy"]["source_paths_in_manifest"] is False
        assert str(sources) not in manifest_text
        assert "not-selected-private-note.txt" not in archive.namelist()
        assert json.loads(archive.read("run/settings.json"))["bad_number"] is None
        diagnostic_records = [
            json.loads(line)
            for line in archive.read("diagnostics/events.jsonl").splitlines()
        ]
        assert diagnostic_records
        assert all(record["test_run_id"] == run_id for record in diagnostic_records)
        items = {item["archive_path"]: item for item in manifest["items"]}
        for archive_path, payload in expected_payloads.items():
            assert archive.read(archive_path) == payload
            assert items[archive_path]["status"] == "included"
            assert items[archive_path]["size_bytes"] == len(payload)
            assert items[archive_path]["sha256"] == hashlib.sha256(payload).hexdigest()
        for suffix in ("ply", "obj", "stl"):
            sidecar = items[f"models/final/scan.{suffix}.json"]
            assert sidecar["relationship"] == {
                "kind": "sidecar_for",
                "target": f"models/final/scan.{suffix}",
            }


def test_complete_run_bundle_streams_file_larger_than_support_attachment_limit(
    tmp_path: Path,
) -> None:
    diagnostics = DiagnosticLog(tmp_path / "logs")
    run_id, run_jsonl = _finished_run(diagnostics)
    large = tmp_path / "large.ply"
    with large.open("wb") as handle:
        handle.seek(DiagnosticLog.MAX_ATTACHMENT_BYTES)
        handle.write(b"x")
    expected_size = DiagnosticLog.MAX_ATTACHMENT_BYTES + 1

    bundle = create_complete_run_bundle(
        tmp_path / "large.zip",
        application_session_id=diagnostics.session_id,
        test_run_id=run_id,
        application_version="test",
        diagnostics_jsonl=run_jsonl,
        artifacts=[
            RunBundleArtifact(
                "models/final/large.ply", large, role="point_cloud", stage="final"
            )
        ],
    )

    with zipfile.ZipFile(bundle) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        item = next(
            item
            for item in manifest["items"]
            if item["archive_path"] == "models/final/large.ply"
        )
        assert item["size_bytes"] == expected_size
        assert archive.getinfo("models/final/large.ply").file_size == expected_size
        assert archive.testzip() is None


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "../scan.ply",
        "models/../scan.ply",
        "/absolute/scan.ply",
        "C:/private/scan.ply",
        "models//scan.ply",
        "models/name:stream.ply",
        "images/NUL.png",
        "manifest.json",
    ],
)
def test_complete_run_bundle_rejects_unsafe_or_reserved_paths(
    tmp_path: Path, unsafe_path: str
) -> None:
    diagnostics = DiagnosticLog(tmp_path / "logs")
    run_id, run_jsonl = _finished_run(diagnostics)
    source = _write(tmp_path / "scan.ply", b"scan")

    with pytest.raises(ValueError):
        create_complete_run_bundle(
            tmp_path / "unsafe.zip",
            application_session_id=diagnostics.session_id,
            test_run_id=run_id,
            application_version="test",
            diagnostics_jsonl=run_jsonl,
            artifacts=[
                RunBundleArtifact(
                    unsafe_path, source, role="point_cloud", stage="final"
                )
            ],
        )


def test_complete_run_bundle_rejects_case_insensitive_duplicate_paths(
    tmp_path: Path,
) -> None:
    diagnostics = DiagnosticLog(tmp_path / "logs")
    run_id, run_jsonl = _finished_run(diagnostics)
    source = _write(tmp_path / "scan.ply", b"scan")

    with pytest.raises(ValueError, match="duplicate"):
        create_complete_run_bundle(
            tmp_path / "duplicate.zip",
            application_session_id=diagnostics.session_id,
            test_run_id=run_id,
            application_version="test",
            diagnostics_jsonl=run_jsonl,
            artifacts=[
                RunBundleArtifact(
                    "models/final/scan.ply",
                    source,
                    role="point_cloud",
                    stage="final",
                ),
                RunBundleArtifact(
                    "MODELS/FINAL/SCAN.PLY",
                    source,
                    role="point_cloud",
                    stage="final",
                ),
            ],
        )


def test_complete_run_bundle_records_missing_and_image_opt_out_explicitly(
    tmp_path: Path,
) -> None:
    diagnostics = DiagnosticLog(tmp_path / "logs")
    run_id, run_jsonl = _finished_run(diagnostics)
    image = _write(tmp_path / "camera.png", b"private image")

    bundle = create_complete_run_bundle(
        tmp_path / "partial.zip",
        application_session_id=diagnostics.session_id,
        test_run_id=run_id,
        application_version="test",
        diagnostics_jsonl=run_jsonl,
        artifacts=[
            RunBundleArtifact(
                "models/final/scan.obj",
                None,
                role="surface_mesh",
                stage="final",
                missing_reason="mesh_not_created",
            ),
            RunBundleArtifact(
                "models/final/scan.stl",
                tmp_path / "not-there.stl",
                role="surface_mesh",
                stage="final",
            ),
            RunBundleArtifact(
                "images/current-camera.png",
                image,
                role="camera_image",
                stage="run",
                required=False,
            ),
        ],
    )

    with zipfile.ZipFile(bundle) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        items = {item["archive_path"]: item for item in manifest["items"]}
        assert manifest["package_status"] == "partial"
        assert items["models/final/scan.obj"]["status"] == "missing"
        assert items["models/final/scan.obj"]["reason"] == "mesh_not_created"
        assert items["models/final/scan.stl"]["reason"] == "file_not_found"
        assert items["images/current-camera.png"]["status"] == "omitted"
        assert items["images/current-camera.png"]["required"] is False
        assert "images/current-camera.png" not in archive.namelist()

    opted_in = create_complete_run_bundle(
        tmp_path / "with-image.zip",
        application_session_id=diagnostics.session_id,
        test_run_id=run_id,
        application_version="test",
        diagnostics_jsonl=run_jsonl,
        artifacts=[
            RunBundleArtifact(
                "images/current-camera.png",
                image,
                role="camera_image",
                stage="run",
            )
        ],
        include_private_images=True,
    )
    with zipfile.ZipFile(opted_in) as archive:
        assert archive.read("images/current-camera.png") == b"private image"
        manifest = json.loads(archive.read("manifest.json"))
        image_item = next(
            item
            for item in manifest["items"]
            if item["archive_path"] == "images/current-camera.png"
        )
        assert image_item["status"] == "included"
        assert image_item["required"] is False


def test_complete_run_bundle_preserves_existing_destination_on_validation_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    diagnostics = DiagnosticLog(tmp_path / "logs")
    run_id, run_jsonl = _finished_run(diagnostics)
    source = _write(tmp_path / "scan.ply", b"scan")
    destination = _write(tmp_path / "existing.zip", b"previous valid output")

    def fail_validation(*_args: object, **_kwargs: object) -> None:
        raise ValueError("injected validation failure")

    monkeypatch.setattr(run_bundle, "_validate_complete_run_bundle", fail_validation)
    with pytest.raises(ValueError, match="injected"):
        create_complete_run_bundle(
            destination,
            application_session_id=diagnostics.session_id,
            test_run_id=run_id,
            application_version="test",
            diagnostics_jsonl=run_jsonl,
            artifacts=[
                RunBundleArtifact(
                    "models/final/scan.ply",
                    source,
                    role="point_cloud",
                    stage="final",
                )
            ],
        )

    assert destination.read_bytes() == b"previous valid output"
    assert list(tmp_path.glob(".existing.zip.*.tmp")) == []


def test_complete_run_bundle_never_replaces_one_of_its_source_artifacts(
    tmp_path: Path,
) -> None:
    diagnostics = DiagnosticLog(tmp_path / "logs")
    run_id, run_jsonl = _finished_run(diagnostics)
    source_and_destination = _write(tmp_path / "evidence.zip", b"source evidence")

    with pytest.raises(ValueError, match="source artifact"):
        create_complete_run_bundle(
            source_and_destination,
            application_session_id=diagnostics.session_id,
            test_run_id=run_id,
            application_version="test",
            diagnostics_jsonl=run_jsonl,
            artifacts=[
                RunBundleArtifact(
                    "project/original.zip",
                    source_and_destination,
                    role="project",
                    stage="original",
                )
            ],
        )

    assert source_and_destination.read_bytes() == b"source evidence"


def test_complete_run_bundle_filters_combined_diagnostics_to_requested_run(
    tmp_path: Path,
) -> None:
    diagnostics = DiagnosticLog(tmp_path / "logs")
    first_id, first_jsonl = _finished_run(diagnostics, "first_only")
    second_id, second_jsonl = _finished_run(diagnostics, "second_only")

    bundle = create_complete_run_bundle(
        tmp_path / "second.zip",
        application_session_id=diagnostics.session_id,
        test_run_id=second_id,
        application_version="test",
        diagnostics_jsonl=first_jsonl + second_jsonl,
        artifacts=[],
    )

    with zipfile.ZipFile(bundle) as archive:
        payload = archive.read("diagnostics/events.jsonl")
        records = [json.loads(line) for line in payload.splitlines()]
        assert records
        assert all(record["test_run_id"] == second_id for record in records)
        assert b"second_only" in payload
        assert b"first_only" not in payload
        assert first_id.encode() not in payload


def test_complete_run_bundle_cancellation_is_atomic_and_removes_temporary_file(
    tmp_path: Path,
) -> None:
    diagnostics = DiagnosticLog(tmp_path / "logs")
    run_id, run_jsonl = _finished_run(diagnostics)
    source = _write(tmp_path / "scan.ply", b"scan-data" * 4096)
    destination = _write(tmp_path / "existing.zip", b"previous package")
    checks = 0

    def cancel_during_write() -> bool:
        nonlocal checks
        checks += 1
        return checks >= 4

    with pytest.raises(RunBundleCancelledError):
        create_complete_run_bundle(
            destination,
            application_session_id=diagnostics.session_id,
            test_run_id=run_id,
            application_version="test",
            diagnostics_jsonl=run_jsonl,
            artifacts=[
                RunBundleArtifact(
                    "models/final/scan.ply", source, "point_cloud", "final"
                )
            ],
            cancel_check=cancel_during_write,
        )

    assert checks >= 4
    assert destination.read_bytes() == b"previous package"
    assert list(tmp_path.glob(".existing.zip.*.tmp")) == []


def test_complete_run_bundle_reports_streaming_write_and_validation_progress(
    tmp_path: Path,
) -> None:
    diagnostics = DiagnosticLog(tmp_path / "logs")
    run_id, run_jsonl = _finished_run(diagnostics)
    source = _write(tmp_path / "scan.ply", b"point-cloud")
    phases: list[str] = []

    create_complete_run_bundle(
        tmp_path / "progress.zip",
        application_session_id=diagnostics.session_id,
        test_run_id=run_id,
        application_version="test",
        diagnostics_jsonl=run_jsonl,
        artifacts=[
            RunBundleArtifact(
                "models/final/scan.ply", source, "point_cloud", "final"
            )
        ],
        progress_callback=lambda phase, _done, _total: phases.append(phase),
    )

    assert any(phase.startswith("Writing ") for phase in phases)
    assert any(phase.startswith("Validating ") for phase in phases)
    assert phases[-1] == "Publishing archive"


def test_unreadable_optional_artifact_is_recorded_instead_of_aborting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    diagnostics = DiagnosticLog(tmp_path / "logs")
    run_id, run_jsonl = _finished_run(diagnostics)
    unreadable = _write(tmp_path / "manual.ply", b"manual")
    original_stat = Path.stat

    def selective_stat(path: Path, *args: object, **kwargs: object):
        if path == unreadable:
            raise PermissionError("locked")
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", selective_stat)
    bundle = create_complete_run_bundle(
        tmp_path / "optional.zip",
        application_session_id=diagnostics.session_id,
        test_run_id=run_id,
        application_version="test",
        diagnostics_jsonl=run_jsonl,
        artifacts=[
            RunBundleArtifact(
                "manual-exports/scan.ply",
                unreadable,
                "point_cloud",
                "manual_export",
                required=False,
            )
        ],
    )

    with zipfile.ZipFile(bundle) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        item = next(
            item
            for item in manifest["items"]
            if item["archive_path"] == "manual-exports/scan.ply"
        )
        assert manifest["package_status"] == "complete"
        assert item["status"] == "missing"
        assert item["reason"] == "source_unreadable_PermissionError"


def test_complete_run_bundle_checks_destination_volume_space_before_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    diagnostics = DiagnosticLog(tmp_path / "logs")
    run_id, run_jsonl = _finished_run(diagnostics)
    source = _write(tmp_path / "scan.ply", b"scan")
    destination = _write(tmp_path / "existing.zip", b"previous package")
    monkeypatch.setattr(
        run_bundle.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(total=100, used=99, free=1),
    )

    with pytest.raises(OSError, match="not enough free space"):
        create_complete_run_bundle(
            destination,
            application_session_id=diagnostics.session_id,
            test_run_id=run_id,
            application_version="test",
            diagnostics_jsonl=run_jsonl,
            artifacts=[
                RunBundleArtifact(
                    "models/final/scan.ply", source, "point_cloud", "final"
                )
            ],
        )

    assert destination.read_bytes() == b"previous package"
    assert list(tmp_path.glob(".existing.zip.*.tmp")) == []


def test_validation_does_not_decompress_every_member_twice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    diagnostics = DiagnosticLog(tmp_path / "logs")
    run_id, run_jsonl = _finished_run(diagnostics)
    source = _write(tmp_path / "scan.ply", b"scan")

    def forbidden_testzip(_archive: zipfile.ZipFile):
        raise AssertionError("testzip would duplicate the streaming validation pass")

    monkeypatch.setattr(zipfile.ZipFile, "testzip", forbidden_testzip)
    bundle = create_complete_run_bundle(
        tmp_path / "single-pass.zip",
        application_session_id=diagnostics.session_id,
        test_run_id=run_id,
        application_version="test",
        diagnostics_jsonl=run_jsonl,
        artifacts=[
            RunBundleArtifact(
                "models/final/scan.ply", source, "point_cloud", "final"
            )
        ],
    )

    assert bundle.is_file()
