# Repository storage and recovery

## Durable source location

- Repository: `https://github.com/auxz2jz/Slot-21`
- Primary branch: `main`
- Project: LaserLine3D, an independent Windows red laser-line 3D scanner
- Current candidate: 0.2.0, software tested and hardware unverified

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

The current local 0.2.0 artifacts are identified in `PROJECT_STATUS.md`:

- packaged executable SHA-256:
  `9DC79C05C5715D0C63B1E2B021CCFCA55EA1AFFA377CF05C0DD718EC51321DBC`
- release ZIP SHA-256:
  `0C665D8EBE52BF2825F34618D563F16498B03679F348DFE28F27FFBB1F1938B6`
- source recovery ZIP SHA-256:
  `EBCD78B908F4EC7AB0B7F252676C73906A63E2EFC34A42ABE9400205937F3487`

The last user-verified baseline remains the partial 0.1.0 physical test. Version
0.2.0 must remain marked as a candidate until the documented hardware test is
completed by the user.
