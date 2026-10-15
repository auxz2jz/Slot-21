# Agent entry point — Slot-21 LaserLine3D

This is a **project-specific routing file**, not a second instruction system. It applies to all repository-aware developers and agents. Preserve every existing development, diagnostics, guided testing, privacy, security, and recovery requirement.

## Mandatory global instructions (canonical source)

Before modifying this project, follow [the Master Instruction Library](https://github.com/auxz2jz/master-instruction-library) in this order:

1. [INSTRUCTION_INDEX.md](https://github.com/auxz2jz/master-instruction-library/blob/main/INSTRUCTION_INDEX.md)
2. [CORE_DEVELOPMENT_RECOVERY_RULES.md](https://github.com/auxz2jz/master-instruction-library/blob/main/CORE_DEVELOPMENT_RECOVERY_RULES.md)
3. [DIAGNOSTICS_STANDARD.md](https://github.com/auxz2jz/master-instruction-library/blob/main/DIAGNOSTICS_STANDARD.md)
4. [GUIDED_TESTING_STANDARD.md](https://github.com/auxz2jz/master-instruction-library/blob/main/GUIDED_TESTING_STANDARD.md)
5. [CODEX_USAGE_EFFICIENCY_STANDARD.md](https://github.com/auxz2jz/master-instruction-library/blob/main/CODEX_USAGE_EFFICIENCY_STANDARD.md), especially sections 20–26 for atomic tasks, account usage, handoffs, and reasoning/model choice.
6. [CROSS_PLATFORM_COLLABORATION_STANDARD.md](https://github.com/auxz2jz/master-instruction-library/blob/main/CROSS_PLATFORM_COLLABORATION_STANDARD.md) only if the project becomes cross-platform or separate platform agents work on it.

Do **not** copy the global rules into this repository; follow their newest applicable requirements and user instructions. If required instructions cannot be read, disclose that limitation before risky work. No instruction file can see unavailable Codex usage percentages or automatically restart a session.

## Existing project-specific sources of truth

- **Current one-page recovery/handoff:** [docs/CODEX_HANDOFF.md](docs/CODEX_HANDOFF.md). Update after each completed atomic task and before interruption-sensitive work; replace stale status, not append transcripts. No `NEXT_TASK_HANDOFF.md` duplicate.
- **Project memory, baselines and bounded task queue/roadmap:** [PROJECT_STATUS.md](PROJECT_STATUS.md). Keep the last **user-confirmed** working version distinct from a software-tested candidate.
- **Hardware and regression verification:** [docs/TESTING.md](docs/TESTING.md) and [docs/DIAGNOSTIC_COVERAGE.md](docs/DIAGNOSTIC_COVERAGE.md).
- **Product/research ideas only, not automatic implementation approval:** [docs/IDEAS_BACKLOG.md](docs/IDEAS_BACKLOG.md).
- **Storage/privacy/backups:** [REPOSITORY_STORAGE.md](REPOSITORY_STORAGE.md) and [`.gitignore`](.gitignore).

## Slot-21 guardrails

- This is a Windows single-camera, stationary V-corner, **hand-swept red laser** scanner. Do not quietly replace its working workflow with the proposed stereo/handheld/LiDAR/structured-light designs.
- Latest published v0.4.0 is **software-tested, awaiting user physical hardware verification**. Preserve the known-good checkpoints and packaging artifacts; do not call a build or synthetic test user-verified.
- User's preferred next research priority is **quantifying and reducing measured depth noise**. Finish the approved 0.4.0 physical-test step before changing geometry; feature ideas are deferred until authorized.
- For any new authorized objective, divide it into small task IDs with dependencies, files, expected results, completion/verification, and next task's recommended model/reasoning. Favor ~2–5-minute tasks when practical; verification and safety outweigh speed.
- Work on **one bounded task at a time**: relevant reading → plan → preserve baseline → minimal change → targeted verification → save/checkpoint → update handoff and task queue → report/reassess.
- Checkpoint after every completed task and before risky/long operations; also during prolonged work at reasonable intervals. Keep raw user images, diagnostic ZIPs, calibration data, private logs and credentials **out of public Git**; maintain protected local backups for Git-ignored artifacts.
- At recovery, read this file and the current handoff, check the **actual local Git status before editing**, preserve uncommitted work, and resume the first unfinished step without repeating completed work. GitHub's remote committed tree **cannot establish the state of another machine's local working tree**.
- Follow master usage thresholds **only when current reliable telemetry exists**; otherwise mark usage unknown, limit the session to one expensive or at most two genuinely small tasks, checkpoint, and stop before more expensive development.
- After each task, provide the concise report defined by the master efficiency standard: COMPLETED, VERIFIED, SAVED, NEXT, RECOMMENDED SETTING, REASON, USAGE, and DECISION. Never claim automatic model switching or precise usage monitoring.

## Explicit continuation boundary

The agent may continue through *already authorized* tasks when checks and usage allow. Stop for unknown/insufficient usage before expensive tasks, failed verification, external physical-test evidence, destructive actions needing approval, or completion of approved scope. Do not invent new features.
