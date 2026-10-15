# Repository storage and recovery

## Durable source location

- Repository: `https://github.com/auxz2jz/Slot-21`
- Primary branch: `main`
- Project: LaserLine3D, an independent Windows red laser-line 3D scanner
- Latest candidate: 0.4.0, software tested and **physical hardware verification pending**

This repository stores maintainable source, automated tests, project status,
recovery instructions, hardware/testing guidance, packaging scripts, and
printable calibration PDFs. Development agents start with `AGENTS.md` and the
Master Instruction Library; then read `docs/CODEX_HANDOFF.md` (current task),
`PROJECT_STATUS.md` (roadmap/baselines), `docs/TESTING.md` and
`docs/DIAGNOSTIC_COVERAGE.md` as relevant. Do not duplicate the handoff.

## Intentionally local/generated content

Python environments, build output, temporary files, diagnostic sessions, user
calibrations, and packaged Windows binaries are excluded from normal Git
history. This prevents machine-specific or private diagnostic data from being
published and avoids GitHub's ordinary per-file limit for the 123 MB release
archive.

The published, software-tested **0.4.0** candidate is identified in `PROJECT_STATUS.md`:

- maintainable-source checkpoint: `2e3cc262e69633894c55c61966302f940185dc2a`
- versioned Windows package: `dist/LaserLine3D_0.4.0/`
- release ZIP: `output/windows/LaserLine3D_Windows_0.4.0_2026-10-14.zip`
- executable SHA-256: `C0144B206778C46974A1947EB4BAADD1AFBBE990966CE93519185F017A4041D7`
- release ZIP SHA-256: `52B195DD3EECC77B3C1B0DF030CE29FD5E528EAA671FE110982414C50750B356`

Those local release files, untracked diagnostic ZIPs, private camera images,
calibration data, and raw scans are **not backed up by a GitHub commit**.
Before risky local operations, inspect their actual filesystem locations,
check hashes where available, and arrange a separate protected backup.
A GitHub API listing cannot verify the user's Windows working-tree status or
that these files still exist. Never automatically reset/clean or upload private
artifacts to public Git.

The following are **historical 0.3.0** local recovery artifact identifiers (not current):

- packaged executable SHA-256:
  `9AA0FDB681EAE7EF6E4FEF92C72917DE8FF36F1AD421E9512F76440460276F1F`
- release ZIP SHA-256:
  `E98B0E487251E583A62020ACDC68138F0083D0F90EAFE37B73775A8086D9CE86`
- exact maintainable-source checkpoint:
  `43ff46e438e73441db0519e7e30b2bc437c36d5d`
- local source recovery ZIP SHA-256:
  `78A578C9638F4B6C3EEFD94DC21FF8C3477BF64B3548368750A90FAFB337737D`

The v0.2.0 and v0.3.0 field evidence is recorded in `PROJECT_STATUS.md` and
`docs/FIELD_TEST_2026-10-13.md`, but it does not establish an accuracy-verified
working baseline. Version 0.4.0 remains a candidate until the user completes
the documented physical hardware test. Prior source/artifact identities must be
preserved as historical recovery points.
