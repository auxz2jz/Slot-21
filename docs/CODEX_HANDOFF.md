# Codex handoff — Slot-21 LaserLine3D

**Read order:** [../AGENTS.md](../AGENTS.md) → applicable global Master Instruction Library → this file → [../PROJECT_STATUS.md](../PROJECT_STATUS.md) task queue → relevant [TESTING.md](TESTING.md)/[DIAGNOSTIC_COVERAGE.md](DIAGNOSTIC_COVERAGE.md). Reuse this file; do not create `NEXT_TASK_HANDOFF.md`. Current-state fields supersede previous handoff wording; historical candidate evidence is retained in project status and Git history.

**COMPLETED TASK:** Bounded read-only review of the 2026-10-16 Standard/Fine flat-board evidence, advancing `S21-AT-004/005` to **PARTIAL / REPEAT REQUIRED**. The two complete-run ZIPs and separate exports were preserved; no scanner source, private scan, calibration, image or bundle was uploaded or altered.

**CURRENT STATUS:** Latest release candidate **LaserLine3D v0.4.0 — SOFTWARE-TESTED and physically exercised, but not accuracy-verified**. Flat-target data now exist, but the oversized target, `10.86 px` corner error, short/degenerate reference-wall support and two readiness overrides make the measured plane residuals provisional. New projector/stereo/LiDAR concepts remain deferred/unapproved research ideas.

**VERIFICATION RESULTS:** Both new bundles passed CRC and every manifest size/SHA-256 check; all separate exports match bundle entries. Standard/Fine accepted `57.5%/71.9%` of frames and retained `197,982/281,553` once-cleaned points. Fine reduced point spacing (`0.613→0.427 mm`) but central once-cleaned best-fit-plane RMS remained `3.37/3.28 mm`; raw MAD stayed about `1.4 mm`, with structured horizontal banding. Degenerate support caused `28.5%/11.6%` of all-frame rejects. Application tests were not rerun because no application code changed. Full method, metrics and limitations are in [../PROJECT_STATUS.md](../PROJECT_STATUS.md).

**LAST VERIFIED BASELINE:** No **user-confirmed accuracy-verified hardware version** is established by available project records. v0.2.0 had user testing but was explicitly *not verified*; v0.3.0 has physical comparison scans but no declared accuracy-verified baseline. Do not conflate these with v0.4.0 software verification.

**LATEST CHECKPOINT:** `main` contains the current documentation/instruction set plus this physical-evidence comparison (verify the authoritative commit with `git rev-parse origin/main`). **Unmodified v0.4.0 application-source baseline:** `2e3cc262e69633894c55c61966302f940185dc2a`. Exact EXE/release ZIP hashes are in [../PROJECT_STATUS.md](../PROJECT_STATUS.md). No application source changed in this task.

**GIT COMMIT / BACKUP STATUS:** The actual Windows checkout was clean and matched `origin/main` after a documentation-only fast-forward before this comparison. Private release folders, complete-run ZIPs, images, calibrations and PLY/OBJ/STL remain protected local/ignored files; GitHub does not back them up. The two input ZIP SHA-256 values were captured locally for identity verification but are intentionally not published with the private evidence. Do not delete, reset, overwrite or upload those artifacts.

**UNFINISHED WORK:** Repeat `S21-AT-004` with a smaller rigid target, acceptable corner solve, stable reference support and no readiness override; then repeat/finalize `S21-AT-005` plane/banding measurements. `S21-AT-003` guided checks remain incomplete and `S21-AT-006` stays deferred pending trustworthy evidence plus explicit development approval.

**KNOWN ERRORS OR BLOCKERS:** New corner pose residual is `10.86 px` versus recommended `≤2.00 px`. The large target leaves short reference-wall spans; many frames have support below `0.003` and are rejected as degenerate. Both scans began with an explicit not-ready override. Plane RMS/p95 therefore combine real banding with calibration/support/target uncertainty and must not drive an algorithm patch yet.

**NEXT EXACT TASK:** Repeat user-side `S21-AT-004` once with a rigid letter-size (`216 × 279 mm`) or smaller matte board in portrait orientation. Remove the target for corner setup; frame all six V landmarks with margin and verify measured V dimensions/90°; target recommended `≤2 px` pose error. Replace the target, draw a tight ROI, capture one valid background, auto-tune once, and wait for five Good previews with both wall spans preferably `80–100+ mm` and support ratio `≥0.006`. Do **not** override readiness. Make one slow uninterrupted **Standard (`0.75 mm`)** sweep, clean once, and save one complete-run ZIP.

**NEXT TASK COMPLETION CRITERIA:** one intact private bundle whose manifest validates; image confirms smaller flat target and generous visible walls; corner error is materially reduced; scan starts without override after five Good previews; raw PLY contains a broad plane. Record target dimensions/material and lighting. No source change is needed.

**RECOMMENDED MODEL / REASONING:** Medium for guiding the controlled capture; High for `S21-AT-005` only after the flat raw cloud exists, because signed plane residuals, banding and calibration uncertainty require geometric interpretation. No automatic model switch is available in this repository.

**USAGE INFORMATION:** Unknown — no reliable current Codex account-usage percentage accessible to this chat. Do not invent usage readings; conservative master-library unknown-usage stop rule applies.

**CONTINUE OR STOP:** **STOP after this evidence-analysis checkpoint.** The next step is the user's smaller-target repeat. Do not start a speculative geometry/filter patch from the confounded large-board data.

## Recovery command and checkpoint discipline

Use `git status --short --branch` and `git log -1 --oneline` **on the actual Windows computer**, inspect uncommitted changes and only relevant changed source before proceeding. Never infer a clean local checkout from a GitHub view. Complete one bounded task, run its targeted verification, commit/push safe authorized changes, refresh *this* handoff and task queue, and record next model/reasoning. For any risky or expensive step, preserve a checkpoint first. Full tests and hardware scans follow [TESTING.md](TESTING.md), not repeated guesses. Save a complete-run ZIP for each controlled physical run, with camera images opt-in and private. Follow the master standard's stop/usage thresholds without claiming nonexistent monitoring or automatic resumption.
