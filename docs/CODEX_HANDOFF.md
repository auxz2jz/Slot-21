# Codex handoff — Slot-21 LaserLine3D

**Read order:** [../AGENTS.md](../AGENTS.md) → applicable global Master Instruction Library → this file → [../PROJECT_STATUS.md](../PROJECT_STATUS.md) task queue → relevant [TESTING.md](TESTING.md)/[DIAGNOSTIC_COVERAGE.md](DIAGNOSTIC_COVERAGE.md). Reuse this file; do not create `NEXT_TASK_HANDOFF.md`. Current-state fields supersede previous handoff wording; historical candidate evidence is retained in project status and Git history.

**COMPLETED TASK:** `S21-AT-001` — repository documentation integration of universal atomic-task planning, usage protection, checkpoints and recovery. **Documentation only**: new `AGENTS.md` delegates to already established Master Instruction Library; `PROJECT_STATUS.md` contains bounded task queue; `REPOSITORY_STORAGE.md` identifies local/private backups. No scanner source was changed.

**CURRENT STATUS:** Latest release candidate **LaserLine3D v0.4.0 — SOFTWARE-TESTED, physical scanner verification pending**. Depth-noise diagnosis is the highest-priority technical issue *after collecting controlled real-world evidence*. New projector/stereo/LiDAR concepts remain deferred/unapproved research ideas.

**VERIFICATION RESULTS:** Previous v0.4.0 release checkpoint reported **97/97 automated tests passed**, **81.42% coverage**, source/packaged self-tests, packaged Qt smoke and validated release ZIP. Those tests were **not rerun** for this documentation-only integration. Remote file readback and task-queue/required-field checks are the verification for `S21-AT-001`; do not claim local Windows or hardware testing.

**LAST VERIFIED BASELINE:** No **user-confirmed accuracy-verified hardware version** is established by available project records. v0.2.0 had user testing but was explicitly *not verified*; v0.3.0 has physical comparison scans but no declared accuracy-verified baseline. Do not conflate these with v0.4.0 software verification.

**LATEST CHECKPOINT:** `main` contains the documentation-only `S21-AT-001` commits (current authoritative commit = remote `main` HEAD; verify via `git rev-parse origin/main` or GitHub commit history). **Unmodified v0.4.0 application-source baseline:** `2e3cc262e69633894c55c61966302f940185dc2a`. Exact EXE/release ZIP hashes are in [../PROJECT_STATUS.md](../PROJECT_STATUS.md). Remote `main` before instruction integration was `d8b63d81e633b206a9a9f3fa89b023dc47b10a4d`.

**GIT COMMIT / BACKUP STATUS:** Documentation saved to connected GitHub repository `auxz2jz/Slot-21`, branch `main`. Root agent-entry commit `c0eeabbbd6dd5d168faa40a7935a93e5b95f44f0`; roadmap queue commit `6561cd6364481723ba2179d64f3fe7b8515a616e`; storage manifest commit `e8fb19872dd087201046181e391b8639a62122f3`. **Local PC Git status is UNKNOWN**: remote API cannot inspect the user's Windows uncommitted work. Local release ZIPs, EXE folders, user calibrations, diagnostic images, run ZIPs and PLY/OBJ/STL need separately protected backup; GitHub doesn't back up ignored/private files. Do not delete, reset, overwrite or upload them.

**UNFINISHED WORK:** `S21-AT-002` local Windows checkout status/backups; `S21-AT-003` guided v0.4.0 physical hardware test; `S21-AT-004` flat-object measured run with complete-run ZIP; `S21-AT-005` depth-noise analysis on actual data. `S21-AT-006` any subsequent code correction is deferred pending evidence and explicit approval. Individual tasks, dependencies, files, measurable checks and model settings are in [../PROJECT_STATUS.md](../PROJECT_STATUS.md).

**KNOWN ERRORS OR BLOCKERS:** Physical v0.4.0 scan quality is not yet validated. Older field runs had visible surface depth noise and ~3–4 px V-corner pose reprojection residuals; no quantitative flat-target noise profile has been supplied for v0.4.0. Source release ZIPs and Windows working-tree status cannot be verified through GitHub alone. See [IDEAS_BACKLOG.md](IDEAS_BACKLOG.md) Sections P/R/S for *deferred* diagnostic hypotheses; do not silently change scanner algorithms or geometry gates.

**NEXT EXACT TASK:** `S21-AT-002` — on the user's Windows checkout, run `git status --short --branch`, inspect current branch/head and any uncommitted or ignored/private artifacts, compare local state against committed `origin/main`, and **preserve** all unknown changes before doing anything else. Only then begin the existing hardware validation tasks, with a matte flat sample used for depth-noise assessment. Do not assume the project can execute on this remote-only tool connection.

**NEXT TASK COMPLETION CRITERIA:** local branch/worktree status recorded accurately; any unfinished local changes identified and preserved; v0.4.0 candidate package and protected backups located or explicitly reported missing; no resetting/cleaning, hardware-code edits, or repeat full builds.

**RECOMMENDED MODEL / REASONING:** Low or Medium for `S21-AT-002` (routine status/artifact reconciliation); increase to High only for contradictory source evidence, substantial geometry diagnostics or a difficult failure. No automatic model switch is available in this repository.

**USAGE INFORMATION:** Unknown — no reliable current Codex account-usage percentage accessible to this chat. Do not invent usage readings; conservative master-library unknown-usage stop rule applies.

**CONTINUE OR STOP:** **STOP after completing `S21-AT-001`**. Remaining work needs access to the local Windows checkout and real scanner test evidence; do not start costly development or create a speculative software patch. Resume at `S21-AT-002` with the actual local Git state.

## Recovery command and checkpoint discipline

Use `git status --short --branch` and `git log -1 --oneline` **on the actual Windows computer**, inspect uncommitted changes and only relevant changed source before proceeding. Never infer a clean local checkout from a GitHub view. Complete one bounded task, run its targeted verification, commit/push safe authorized changes, refresh *this* handoff and task queue, and record next model/reasoning. For any risky or expensive step, preserve a checkpoint first. Full tests and hardware scans follow [TESTING.md](TESTING.md), not repeated guesses. Save a complete-run ZIP for each controlled physical run, with camera images opt-in and private. Follow the master standard's stop/usage thresholds without claiming nonexistent monitoring or automatic resumption.
