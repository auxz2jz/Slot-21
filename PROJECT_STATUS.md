# Project status and verified baselines

## Scope

This is an independent Windows project for hand-swept red laser-line 3D
scanning. It does not use or modify the separate photogrammetry project.

## Recovery checkpoint — 2026-10-13

- **Latest candidate:** 0.3.0, **CANDIDATE / SOFTWARE TESTED / HARDWARE
  UNVERIFIED**. Do not describe a build, launch, synthetic test, or earlier
  physical scan as verification of this candidate.
- **Last user field evidence:** two 0.2.0 physical scans produced usable data
  but exposed camera-evidence, corner interaction, reference-support, coverage,
  and log-retention problems. Version 0.2.0 remains **USER TESTED / NOT
  VERIFIED**. Sanitized findings are in `docs/FIELD_TEST_2026-10-13.md`.
- **Current task:** corrective implementation, automated tests, source
  self-test, Windows build, packaged Qt smoke test, packaged scan/export
  self-test, release ZIP creation, and ZIP integrity validation are complete.
  The exact next action is the guided 0.3.0 physical retest in
  `docs/TESTING.md`.
- **Durable repository:** `https://github.com/auxz2jz/Slot-21`, branch `main`.
  The final 0.3.0 source checkpoint commit is recorded below after publication.
- **Private evidence:** raw camera images, diagnostic archives, calibrations,
  scans, environments, and Windows binaries remain local and outside normal
  Git history. No user scan or diagnostic file was deleted during this build.

## What 0.3.0 changes

### Decisive, bounded diagnostics

- automatically timed camera-property snapshots at open/settings/background/
  scan/pause/finish/export boundaries;
- raw values plus OpenCV property IDs and `reported`, `unavailable`, or
  `zero_or_unsupported` status for exposure, gain, brightness, contrast,
  saturation, hue, gamma, sharpness, backlight, autofocus/focus, automatic and
  manual white balance, temperature, iris, zoom, FourCC, and capture buffer;
- privacy-safe full-frame/object-ROI/outside-ROI BGR, gray, and HSV percentiles,
  clipping, contrast, and applicable sharpness measurements; large images use
  a deterministic bounded sample and no pixels are retained;
- in-app key/click/wheel context, canvas zoom/pan/point/ROI operations, settings,
  workflow actions, operation results, and failures. Key logging never reads
  typed text; printable keys share a non-identifying category. Global activity,
  clipboard data, image pixels, and point clouds are not collected implicitly;
- an 8 MiB active JSONL cap, 48 MiB stored-session budget, bounded event sizes,
  first/recent/failure/latest record preservation, complete event counts, and
  attachment/support-ZIP size limits;
- sampled scan detail plus bounded complete totals/distributions for object,
  left wall, right wall, unclassified and candidate pixels inside/outside the
  green ROI. This replaces the 150 MB per-frame log seen in the field test.

### Calibration and scan protection

- pointer-anchored wheel zoom; short-click landmark placement deferred until
  mouse release; left/right/middle drag panning without accidental points;
  landmark Undo/reset, ROI selection, and final view state recorded;
- stable machine reason codes for missing wall/object, no line, ambiguous/no
  stable plane, excessive residual, failed ray intersection, shallow angle,
  depth, and reference-volume rejection;
- rejected plane fits retain attempted support ratio, RMS/median residual,
  covariance eigenvalues, inlier counts, wall spans, normal uncertainty, and
  attempted/valid RANSAC model counts;
- live wall counts/spans, plane RMS, support ratio and triangulation angle;
- a scan-readiness gate requiring five recent stable frames, unchanged
  background, recommended `0.006` support margin, and acceptable corner error,
  or an explicit logged **Start anyway (diagnostic run)** override;
- automatic pause after 50 consecutive frames without a usable laser line;
- appearance-changing camera controls invalidate the laser-off background and
  pause an active scan; focus/autofocus/zoom also invalidate calibration.
  Informational changes such as sensor temperature are logged without false
  invalidation;
- low-angle guidance says to translate the laser line up/down while keeping
  long wall segments, not pivot it toward the centre seam.

The geometry safety cutoffs were not weakened: minimum triangulation angle is
still 5 degrees and the plane-support guard is still 0.003.

## Software-tested 0.3.0 candidate baseline

Build date: 2026-10-13 (America/Los_Angeles; UTC artifacts may show 2026-10-14).

- Python 3.12.14
- NumPy 2.5.3
- OpenCV 4.14.0.94 (headless runtime)
- SciPy 1.18.1
- PySide6 Essentials / Qt 6.12.0
- PyInstaller 6.22.3 with hooks 2026.8
- 61/61 automated tests passed in 7.03 seconds in the final build pipeline
- standalone source/prebuild self-test passed: 24/28 frames accepted, 4,316
  fused points, 8,334 triangles, 1.4491 mm median virtual-plane error
- packaged Qt smoke test passed: real seven-page main window, application
  version 0.3.0, both printables present, clean close
- packaged scan/export self-test exited 0 and produced PLY/STL artifacts
- required `_internal/cv2/config.py` and `config-3.py` are present
- published folder: `dist/LaserLine3D_0.3.0`
- package: 346 files, 311,297,581 bytes
- release ZIP:
  `output/windows/LaserLine3D_Corrective_Diagnostics_0.3.0_2026-10-13.zip`
- ZIP: 361 entries including directories, 123,351,336 bytes; all entries were
  decompressed and read successfully; uncompressed file bytes exactly matched
  311,297,581; no unsafe paths; required EXE/OpenCV configs/PDFs present
- executable SHA-256:
  `9AA0FDB681EAE7EF6E4FEF92C72917DE8FF36F1AD421E9512F76440460276F1F`
- release ZIP SHA-256:
  `E98B0E487251E583A62020ACDC68138F0083D0F90EAFE37B73775A8086D9CE86`
- the executable embedded in the ZIP has the same SHA-256 as the published EXE
- exact maintainable-source checkpoint:
  `43ff46e438e73441db0519e7e30b2bc437c36d5d`
- local source recovery ZIP:
  `output/windows/LaserLine3D_Source_Candidate_0.3.0_2026-10-13.zip`
  (153,493 bytes), SHA-256
  `78A578C9638F4B6C3EEFD94DC21FF8C3477BF64B3548368750A90FAFB337737D`

The build initially could not rename the older `dist/LaserLine3D` directory.
Inspection showed that directory is also the user's live data location and
contains calibration JSON, diagnostic ZIPs, and scan exports. All of it was
preserved. Publication was changed to a versioned package folder and
`dist/CURRENT_PACKAGE.txt`; `run_scanner.bat` uses that marker and falls back to
the older canonical package only when no marker exists. The revised build then
passed end to end without touching the user-data-bearing folder.

The first final rebuild also encountered a Windows lock on a reused pytest
temporary directory. The new native-command exit checks stopped publication as
intended. The build now gives every run a unique ignored pytest workspace; the
subsequent complete pipeline passed and produced the hashes above.

## Historical baselines

- **0.2.0 software-tested / user-tested / not verified:** source commit
  `f2e4f451ab0a08423b0c3ebda441aa36ecca9cf1`; 35/35 tests; EXE SHA-256
  `9DC79C05C5715D0C63B1E2B021CCFCA55EA1AFFA377CF05C0DD718EC51321DBC`;
  release ZIP SHA-256
  `0C665D8EBE52BF2825F34618D563F16498B03679F348DFE28F27FFBB1F1938B6`.
- **0.1.0 partial user test:** the Logitech camera opened, lens/corner setup
  completed, and a point cloud began forming. This was not a complete hardware
  or accuracy verification.

## Known limitations and deferred work

- One fixed-camera pass measures only the visible surface. Moving or rotating
  the object in the same scan is still invalid because no transform is measured.
  Use separate passes until indexed-turntable registration exists.
- The green ROI remains the default object-triangulation area. An experimental
  full-field option is deferred until the new evidence can prove it does not
  turn wall/background returns into object points.
- Background-point selection/deletion, coverage heat maps, draggable existing
  landmarks, magnified crosshair/keyboard nudging, ArUco corner automation,
  automatic multi-view stitching, and turntable fusion remain planned.
- Generic cross-camera exposure/focus/RGB/zoom sliders remain intentionally
  absent because driver support and units are not portable. Use the native
  Windows camera dialog; changing focus/zoom requires both calibrations again.
- The support bundle still has no persistent in-app guided-test wizard or
  generated TXT/JSON test report. The documented procedure and structured ZIP
  are the current evidence path.
- Clean-PC packaging has not yet been independently tested on a second Windows
  machine, and physical measurement accuracy remains unverified.

## Next validation gate

1. Extract the 0.3.0 ZIP into a fresh directory; never merge `_internal` files.
2. Follow every step in `docs/TESTING.md`, including anchored zoom/pan,
   readiness return/override, no-line watchdog, and diagnostics privacy checks.
3. Repeat controlled flat-card, known-block, and object scans with locked
   camera controls and unchanged lighting/fixture/ROI.
4. Upload the new diagnostic ZIP and exports for comparison.
5. Record a Windows hardware-verified baseline only if the physical checks and
   known-dimension measurements pass.
