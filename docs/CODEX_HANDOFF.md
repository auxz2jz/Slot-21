# Codex handoff — Slot-21 LaserLine3D

**Read order:** [../AGENTS.md](../AGENTS.md) → applicable global Master Instruction Library → this file → [../PROJECT_STATUS.md](../PROJECT_STATUS.md) task queue → relevant [TESTING.md](TESTING.md)/[DIAGNOSTIC_COVERAGE.md](DIAGNOSTIC_COVERAGE.md). Reuse this file; do not create `NEXT_TASK_HANDOFF.md`. Current-state fields supersede previous handoff wording; historical candidate evidence is retained in project status and Git history.

**COMPLETED TASK:** `S21-CAM-003` Windows packaging. The guarded build published `dist/LaserLine3D_0.5.0` and `output/windows/LaserLine3D_Windows_0.5.0_2026-10-20.zip` without overwriting v0.4.0. Required OpenCV files, package/ZIP integrity and embedded EXE identity were verified.

**CURRENT STATUS:** Packaged **v0.5.0 is the latest software-tested candidate**, not user/hardware verified. Published v0.4.0 remains preserved, software-tested and physically exercised but not accuracy-verified. No B029201 mode/control is yet physically verified; all old Logitech lens/corner/background data are invalid for the new camera. Geometry algorithms are unchanged.

**VERIFICATION RESULTS:** Final build pipeline: `108 passed` in 7.92 s. Source self-test: PASS, 24 accepted frames, 4,316 points, 8,334 triangles, 1.4491 mm median synthetic depth error. Packaged Qt smoke: PASS, v0.5.0, seven pages and both printables. Packaged self-test exited 0 and produced a 4,316-vertex PLY and 8,334-triangle STL. Package: 346 files / 311,354,947 bytes. ZIP: 361 entries / 123,409,022 bytes, full CRC/decompression PASS, one safe top-level folder. Hardware mode/control support remains pending.

**LAST VERIFIED BASELINE:** No **user-confirmed accuracy-verified hardware version** is established by available project records. v0.2.0 had user testing but was explicitly *not verified*; v0.3.0 has physical comparison scans but no declared accuracy-verified baseline. Do not conflate these with v0.4.0 software verification.

**LATEST CHECKPOINT:** v0.5.0 source is commit `c58ae8aefbb06ac8d9fc189b6b374af0d569f0c9`. Packaged EXE SHA-256: `1244BD7A821622BB3C0F831A7953A5984DF2471A1951AE4D724162647CD8E065`; release ZIP SHA-256: `AFEE6CEF79B66F4E6A37253850AFBFB22028E698E873830AC316892ABC9BAFB2`. **Preserved v0.4.0 source baseline:** `2e3cc262e69633894c55c61966302f940185dc2a`; its EXE/ZIP hashes were rechecked unchanged.

**GIT COMMIT / BACKUP STATUS:** The actual Windows checkout was clean at `c58ae8a` and matched `origin/main` before packaging. Build outputs are ignored/local; only public recovery documentation is changed for the packaging checkpoint. Private complete-run ZIPs, images, calibrations and PLY/OBJ/STL were not uploaded. v0.4.0 remains locally recoverable and unchanged.

**UNFINISHED WORK:** `S21-CAM-004` requires the user's B029201: physically test DirectShow MJPEG at 3264 × 2448 / 15 fps and 1920 × 1080 / 30 fps, then apply/read back selected autofocus/focus, exposure/gain and white-balance controls and save a compact diagnostic ZIP. Only after review should new checkerboard/corner/background calibration begin.

**KNOWN ERRORS OR BLOCKERS:** No physical B029201 read-back exists yet. High-resolution USB 2.0 modes normally require MJPEG and may run at only 15 fps; the driver may substitute another mode. OpenCV does not reliably expose camera model names, supported-property ranges, or complete UVC mode lists. Existing 9.45 px corner evidence belongs to the old camera/setup and cannot be reused. A live Master Instruction Library Git check failed with Windows Schannel `SEC_E_NO_CREDENTIALS`; this task used the synchronized local master checkpoint `359d26f49e86480fd647f63f4bb56f529008d9b6`.

**NEXT EXACT TASK:** `S21-CAM-004`: run the bounded B029201 mode/control test, save one compact diagnostic ZIP, and compare requested versus actual mode and property read-back. Do not reuse old calibration or begin accuracy testing yet.

**NEXT TASK COMPLETION CRITERIA:** diagnostic evidence identifies accepted/substituted resolution, FPS and FourCC for both requested modes and applied/substituted/refused/unreported results for the selected controls. The camera profile can be saved and loaded without automatic apply. Hardware support remains CANDIDATE until this passes.

**RECOMMENDED MODEL / REASONING:** Medium for concise diagnostic comparison; raise to High only if driver results are contradictory across backends. No source change should start before evidence review.

**USAGE INFORMATION:** Unknown — no reliable current Codex account-usage percentage accessible to this chat. Do not invent usage readings; conservative master-library unknown-usage stop rule applies.

**CONTINUE OR STOP:** **STOP after the `S21-CAM-003` checkpoint.** Usage telemetry is unavailable, packaging is complete, and the next task requires user hardware evidence.

## Recovery command and checkpoint discipline

Use `git status --short --branch` and `git log -1 --oneline` **on the actual Windows computer**, inspect uncommitted changes and only relevant changed source before proceeding. Never infer a clean local checkout from a GitHub view. Complete one bounded task, run its targeted verification, commit/push safe authorized changes, refresh *this* handoff and task queue, and record next model/reasoning. For any risky or expensive step, preserve a checkpoint first. Full tests and hardware scans follow [TESTING.md](TESTING.md), not repeated guesses. Save a complete-run ZIP for each controlled physical run, with camera images opt-in and private. Follow the master standard's stop/usage thresholds without claiming nonexistent monitoring or automatic resumption.
