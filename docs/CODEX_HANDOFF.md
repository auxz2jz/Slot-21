# Codex handoff — Slot-21 LaserLine3D

**Read order:** [../AGENTS.md](../AGENTS.md) → applicable global Master Instruction Library → this file → [../PROJECT_STATUS.md](../PROJECT_STATUS.md) task queue → relevant [TESTING.md](TESTING.md)/[DIAGNOSTIC_COVERAGE.md](DIAGNOSTIC_COVERAGE.md). Reuse this file; do not create `NEXT_TASK_HANDOFF.md`. Current-state fields supersede previous handoff wording; historical candidate evidence is retained in project status and Git history.

**COMPLETED TASK:** `S21-CAM-001` high-resolution UVC mode negotiation for the new Arducam B029201. The v0.5.0 source camera page now offers additional modes through 3840 × 2160, requested 1–120 fps, MJPEG/YUY2/default transport, actual resolution/FPS/FourCC read-back, clear substituted/unverified warnings, and `camera_mode_negotiated` diagnostics. The native driver dialog remains available.

**CURRENT STATUS:** Published **v0.4.0 remains preserved, software-tested and physically exercised but not accuracy-verified**. Source `main` is now an unreleased **v0.5.0 software-tested development candidate**; no 0.5.0 EXE/ZIP exists and no B029201 mode is physically verified. All old Logitech lens/corner/background data are invalid for the new camera. Geometry algorithms are unchanged.

**VERIFICATION RESULTS:** Targeted camera/UI tests: `11 passed`. Full automated suite: `101 passed`. Deterministic source self-test: PASS, 24 accepted frames, 4,316 points, 8,334 triangles, 1.4491 mm median synthetic depth error. v0.5.0 offscreen Qt smoke: PASS, seven pages, checkerboard/setup-guide resources present. Hardware mode negotiation remains pending because OpenCV/Windows drivers cannot reliably enumerate or prove every advertised UVC mode without opening the actual device.

**LAST VERIFIED BASELINE:** No **user-confirmed accuracy-verified hardware version** is established by available project records. v0.2.0 had user testing but was explicitly *not verified*; v0.3.0 has physical comparison scans but no declared accuracy-verified baseline. Do not conflate these with v0.4.0 software verification.

**LATEST CHECKPOINT:** `main` contains the v0.5.0 camera-mode source candidate and current handoff (verify the authoritative commit with `git rev-parse origin/main`). **Preserved v0.4.0 application-source baseline:** `2e3cc262e69633894c55c61966302f940185dc2a`; exact published EXE/release ZIP hashes remain in [../PROJECT_STATUS.md](../PROJECT_STATUS.md).

**GIT COMMIT / BACKUP STATUS:** The actual Windows checkout was clean and matched `origin/main` before `S21-CAM-001`. Only source/tests/public documentation were changed. Private release folders, complete-run ZIPs, images, calibrations and PLY/OBJ/STL remain protected local/ignored files and were not uploaded. The 0.4.0 package remains recoverable and must not be overwritten by a future build.

**UNFINISHED WORK:** `S21-CAM-002` is authorized and pending: add in-program camera controls plus named JSON profiles with apply/read-back evidence and correct calibration/background invalidation, while retaining **Camera driver settings…**. After profiles are verified and v0.5.0 is packaged, physically test B029201 modes/controls, then perform entirely new checkerboard and corner calibrations before resuming `S21-AT-004/005`.

**KNOWN ERRORS OR BLOCKERS:** No physical B029201 read-back exists yet. High-resolution USB 2.0 modes normally require MJPEG and may run at only 15 fps; the driver may substitute another mode. OpenCV does not reliably expose camera model names, supported-property ranges, or complete UVC mode lists, so profile controls must never invent ranges or claim a set succeeded without read-back. Existing 9.45 px corner evidence belongs to the old camera/setup and cannot be reused.

**NEXT EXACT TASK:** `S21-CAM-002`: define a versioned camera-profile JSON model, add explicit in-app controls only for the measurement-relevant UVC properties already monitored, apply them through the camera thread, read every value back, display applied/refused/substituted status, preserve the native dialog, and add save/load plus diagnostic/guided-test coverage. Geometry-changing focus/autofocus/zoom values must invalidate lens/corner calibration; appearance values must invalidate the laser background.

**NEXT TASK COMPLETION CRITERIA:** profile schema validates and round-trips; apply requests and actual read-back/mismatches are visible and logged; unsupported/refused properties remain honest; invalidation tests pass; existing full suite, self-test and Qt smoke remain green. Hardware support remains CANDIDATE until tested on the B029201.

**RECOMMENDED MODEL / REASONING:** High for `S21-CAM-002` because asynchronous driver apply/read-back, partial support, profile persistence and geometry/background invalidation interact; reduce to Medium for packaging/documentation after tests pass. Checkpoint exists before starting.

**USAGE INFORMATION:** Unknown — no reliable current Codex account-usage percentage accessible to this chat. Do not invent usage readings; conservative master-library unknown-usage stop rule applies.

**CONTINUE OR STOP:** **STOP after the `S21-CAM-001` checkpoint.** Usage telemetry is unavailable and this was the session's bounded development task. Resume with `S21-CAM-002`; do not build/publish v0.5.0 until profiles and verification are complete.

## Recovery command and checkpoint discipline

Use `git status --short --branch` and `git log -1 --oneline` **on the actual Windows computer**, inspect uncommitted changes and only relevant changed source before proceeding. Never infer a clean local checkout from a GitHub view. Complete one bounded task, run its targeted verification, commit/push safe authorized changes, refresh *this* handoff and task queue, and record next model/reasoning. For any risky or expensive step, preserve a checkpoint first. Full tests and hardware scans follow [TESTING.md](TESTING.md), not repeated guesses. Save a complete-run ZIP for each controlled physical run, with camera images opt-in and private. Follow the master standard's stop/usage thresholds without claiming nonexistent monitoring or automatic resumption.
