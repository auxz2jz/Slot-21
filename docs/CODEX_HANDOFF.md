# Codex handoff

- Project: Slot-21 LaserLine3D Scanner; active objective is the Windows 0.4.0 test-run release.
- Stage: 0.4.0 implementation, release hardening, full regression, Windows packaging, archive validation, and the maintainable-source commit are complete; final documentation publication remains.
- Branch/commit: `main`; 0.4.0 implementation checkpoint `d28477bdedeef80cb34f670c90f470524482668f`.
- Completed: Standard/Fine density modes, 10k/50k preview limits, repeated-Finish cleanup preservation, run-scoped diagnostics, complete-run ZIP backend/UI, manual export tracking, and version bump to 0.4.0. Release hardening now preserves the raw fused cloud before cleanup, avoids in-memory `.llscan` compression, stages beside the destination, checks free space, validates ZIPs in one streaming pass, supports cancel/progress, records package attempts, reports partial packages honestly, and warns before closing unsaved evidence.
- Verified after final hardening: final build pipeline 97/97; coverage 81.42% (75% required); source/prebuild/packaged scan self-tests passed with 24 frames, 4,316 points, 8,334 triangles, and 1.4491 mm median synthetic depth error; source and packaged Qt smoke passed on 0.4.0 with all seven pages and printables. Focused final review found no release blocker.
- Active files: `src/laserline3d/{diagnostics.py,models.py,project_store.py,run_bundle.py,ui/main_window.py,ui/pages.py,ui/widgets.py}`, related tests, `README.md`, `PROJECT_STATUS.md`, and docs.
- Decisions: preserve calibration/background between test runs; freeze density after scan evidence; keep measured RGB; ZIP includes explicit run artifacts only; private images require opt-in; preserve reviewed cleanup when Finish is repeated; a partial ZIP remains retryable and never claims missing formats were included.
- Release artifacts: `dist/LaserLine3D_0.4.0` (346 files; 311,338,437 bytes) and `output/windows/LaserLine3D_Windows_0.4.0_2026-10-14.zip` (361 entries; 123,391,819 bytes). EXE SHA-256 `C0144B206778C46974A1947EB4BAADD1AFBBE990966CE93519185F017A4041D7`; ZIP SHA-256 `52B195DD3EECC77B3C1B0DF030CE29FD5E528EAA671FE110982414C50750B356`; archive CRC/decompression and embedded EXE hash passed.
- Remaining risk: long model-format generation is still synchronous, though ZIP compression/validation now reports progress and can be cancelled. Physical scanner validation is still required.
- Uncommitted changes: only this final commit-reference documentation update; do not reset or discard.
- Exact next step: commit this final documentation checkpoint and push `main` to Slot-21.
- Resume commands: `git status --short --branch`; targeted searches in `src/laserline3d/ui/main_window.py` and `src/laserline3d/run_bundle.py`; tests use workspace-local `TMP`, `TEMP`, and pytest cache under `tmp/`.
- User decisions required: none currently. Physical scanner validation remains required after the software build.
