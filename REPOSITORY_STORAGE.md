# Repository storage and recovery

## Durable source location

- Repository: `https://github.com/auxz2jz/Slot-21`
- Primary branch: `main`
- Project: LaserLine3D, an independent Windows red laser-line 3D scanner
- Current candidate: 0.3.0, software tested and hardware unverified

This repository stores the maintainable source, automated tests, project status,
recovery instructions, hardware/testing guidance, packaging scripts, and
printable calibration PDFs. Start recovery with `PROJECT_STATUS.md`, then
`README.md`, `docs/TESTING.md`, and `docs/DIAGNOSTIC_COVERAGE.md`.

## Intentionally local/generated content

Python environments, build output, temporary files, diagnostic sessions, user
calibrations, and packaged Windows binaries are excluded from normal Git
history. This prevents machine-specific or private diagnostic data from being
published and avoids GitHub's ordinary per-file limit for the 123 MB release
archive.

The current local 0.3.0 artifacts are identified in `PROJECT_STATUS.md`:

- packaged executable SHA-256:
  `9AA0FDB681EAE7EF6E4FEF92C72917DE8FF36F1AD421E9512F76440460276F1F`
- release ZIP SHA-256:
  `E98B0E487251E583A62020ACDC68138F0083D0F90EAFE37B73775A8086D9CE86`
- source checkpoint commit: pending the final 0.3.0 Git checkpoint

The latest physical evidence is the two-test 0.2.0 field run, which is user
tested but not verified. Version 0.3.0 must remain marked as a candidate until
the documented hardware test is completed by the user.
