# Project status and verified baselines

## Scope

This is a new, independent Windows project for hand-swept red laser-line 3D
scanning. It does not use or modify the separate photogrammetry project.

## Recovery checkpoint — 2026-10-12

- **Last user-verified baseline:** partial physical test of Windows candidate
  0.1.0. The camera opened, lens/corner setup completed, and a point cloud began
  forming. This is not a complete hardware or accuracy verification.
- **Latest candidate:** 0.2.0, **CANDIDATE / SOFTWARE TESTED / HARDWARE
  UNVERIFIED**. It must not replace the user-verified baseline until the user
  physically tests it.
- **Current task:** **DONE for software delivery.** The laser-tuning,
  camera-guidance, scan-state, dark-preview, camera-reconnect safety, and
  support-diagnostics update requested after the 0.1.0 field test is packaged.
- **Completed plan:** stale calibration/background data is invalidated across
  camera reconnects; old camera/scan callbacks are generation-gated; exported
  diagnostics redact private local path prefixes; targeted/full tests, source
  self-test, packaged Qt smoke test, and packaged scan/export self-test passed;
  the versioned ZIP was recreated and verified against the published EXE.
- **Changed areas:** diagnostics, camera/scan lifecycle, laser/scan UI,
  detection assistance, point-cloud preview, tests, hardware/testing guidance,
  and this checkpoint.
- **Evidence already received:** screenshots of the earlier packaged Qt/OpenCV
  startup failures and the user's 0.1.0 hands-on report covering calibration,
  tuning confusion, laser bloom/noise, scan controls, dark preview, and object
  movement questions.
- **Interrupted operation recovered:** the second 0.2.0 package build completed
  successfully, but its versioned ZIP was not regenerated and its hashes were
  not recorded. Audit then found the three targeted safety/privacy corrections
  listed in the current plan; the stale ZIP must not be distributed.
- **Durable source repository:** `https://github.com/auxz2jz/Slot-21`, branch
  `main`. Maintainable source, tests, documentation, recovery state, and the
  printable calibration PDFs are stored there. Generated environments, build
  folders, temporary data, and Windows packages remain outside normal Git
  history; their identities and hashes are recorded in this checkpoint.
- **Published 0.2.0 source checkpoint:** commit
  `f2e4f451ab0a08423b0c3ebda441aa36ecca9cf1`. This is the exact maintainable
  source, tests, documentation, and printable set used for this candidate.
- **Exact next action:** the user should extract the 0.2.0 ZIP into a fresh
  folder and follow **Test This Version — Windows candidate 0.2.0** in
  `docs/TESTING.md`, then upload the diagnostics ZIP from the first failing or
  questionable run.

## Current implementation: 0.2.0 tuning and diagnostics baseline

Implemented:

- fixed Logitech/UVC camera capture using DirectShow, Media Foundation, or auto;
- guided checkerboard lens calibration with resolution binding;
- measured two-wing reference-corner pose calibration with a separate fresh
  object frame for ROI selection;
- bundled exact-scale US Letter checkerboard and illustrated fixture guide;
- zoom-and-pan landmark picking with an in-app numbered six-point diagram;
- laser-off background capture with explicit stable-room-lighting guidance and
  background-mismatch detection;
- red-dominance and background-assisted stripe detection with subpixel centroid;
- numbered laser thresholds, plain-language explanations, one-click defaults,
  and conservative laser-on auto-suggest;
- native Windows camera controls plus raw diagnostic reporting for autofocus,
  focus, exposure, gain, brightness, contrast, saturation, sharpness, white
  balance, and zoom (without pretending device-specific ranges are universal);
- camera-generation guards, reconnect invalidation, and cancellation of partial
  background capture so old-camera frames/settings cannot contaminate a scan;
- per-frame recovery of the handheld laser plane from both reference wings;
- frame rejection for missing references, unstable/degenerate plane support,
  high residual, wrong resolution, unsafe depth, and low triangulation angle;
- point-cloud accumulation, voxel downsampling, statistical cleanup;
- conservative camera-visible open-surface meshing;
- binary PLY, coloured OBJ, binary STL, and JSON export metadata;
- portable `.llscan` project snapshots;
- unambiguous Start/Scanning/Resume/Finishing controls and a strict warning that
  moving the object creates unregistered/ghosted geometry;
- high-contrast point-cloud preview for dark captured colors without changing
  project or export RGB data;
- structured JSONL diagnostics for settings, actions, per-frame scan outcomes,
  rejection reasons, and failures, plus a user-exported support ZIP with an
  explicit opt-in choice for camera images;
- ordered event/session IDs, monotonic timing, scan operation IDs, app version,
  bounded log retention, main/thread crash capture, standard-JSON normalization,
  path-prefix redaction, and an atomic locked diagnostic snapshot;
- a diagnostic coverage map and exact 0.2.0 guided hardware-test procedure;
- deterministic synthetic no-camera scan and automated tests;
- PyInstaller onedir build definition and Windows setup/run scripts.
- staged package publication with OpenCV-file checks, packaged smoke tests, and
  preservation of the previous release before replacing `dist/LaserLine3D`.

## Verified baseline tracking

**SOFTWARE-TESTED CANDIDATE BASELINE:** Version 0.2.0, 2026-10-12.

- Python 3.12.14
- NumPy 2.5.3
- OpenCV 4.14.0.94 (headless runtime)
- SciPy 1.18.1
- PySide6 Essentials 6.12.0
- 35/35 automated tests passed in 7.01 seconds in the final release build pipeline
- standalone source self-test passed: 24/28 frames accepted, 4,316 fused
  points, 8,334 triangles, 1.4491 mm median error against the noisy virtual
  flat-surface truth
- PyInstaller 6.22.3 onedir build completed
- packaged `LaserLine3D.exe` self-test exited 0 and produced PLY/STL artifacts
- packaged Qt smoke test constructed the real seven-page main window using
  Qt 6.12.0, reported application version 0.2.0, verified both bundled
  printables, processed events, and closed cleanly
- incompatible Poppler ICU DLLs that previously caused `QtCore` to fail at
  startup are excluded from the release folder
- release folder: `dist/LaserLine3D`, 346 files, 311,257,541 bytes (296.8 MiB)
- complete versioned ZIP: 361 entries, 123,306,871 bytes; required OpenCV
  configuration files and both printable PDFs present; no unsafe archive paths;
  embedded executable hash exactly matches the published folder
- executable SHA-256:
  `9DC79C05C5715D0C63B1E2B021CCFCA55EA1AFFA377CF05C0DD718EC51321DBC`
- release ZIP SHA-256:
  `0C665D8EBE52BF2825F34618D563F16498B03679F348DFE28F27FFBB1F1938B6`
- source recovery checkpoint:
  `output/windows/LaserLine3D_Source_Candidate_0.2.0_2026-10-12.zip`; its exact
  integrity hash is stored in the adjacent `.zip.sha256` sidecar so the archive
  can contain this final checkpoint without a self-referential hash.

This baseline verifies software with deterministic synthetic geometry. Its
exact maintainable source checkpoint is commit
`f2e4f451ab0a08423b0c3ebda441aa36ecca9cf1` in the durable source repository.

**WINDOWS HARDWARE LAST VERIFIED BASELINE:** Partial user field test of the
previous 0.1.0 build: the Logitech camera opened, lens/corner setup completed,
and a point cloud began forming. That test exposed tuning clarity, laser bloom,
scan-state, and dark-preview problems addressed in 0.2.0. Version 0.2.0 and
measurement accuracy still require a physical retest; clean-PC packaging has not
been independently tested.

Compilation, a successful launch, or the synthetic test must never be recorded
as hardware verification.

## Known limitations, findings, and rejected approaches

- One fixed-camera pass measures only the visible front surface. Rotating or
  translating the object inside the same scan is rejected as a workflow because
  no transform is measured; it creates doubled/ghosted geometry. Use separate
  passes until indexed-turntable registration exists.
- Generic cross-camera focus/exposure/RGB/zoom sliders were intentionally not
  added. Driver support and value ranges are not portable; the native Windows
  driver dialog plus raw reported values is safer. Webcam zoom is commonly a
  crop and any focus/zoom/crop change requires recalibration.
- The earlier `QtCore` startup failure was traced to incompatible Poppler ICU
  DLLs collected from the build host. The packaging definition excludes them
  and verifies the real packaged Qt window before publication.
- An earlier 0.2.0 release ZIP was created before the final queued-frame guard.
  Audit detected the hash mismatch; that ZIP was superseded by the verified ZIP
  recorded above rather than being distributed.
- The first attempted 0.2.0 publication correctly stopped because the older app
  was still running. The tested staging package was preserved, the app was
  closed, and publication was rerun without deleting the previous package.
- The application does not yet provide a persistent in-app multi-step guided
  test/report wizard or a scan-progress stall watchdog. The documented guided
  procedure and structured support ZIP are the current candidate evidence path.

## Next validation gate

1. Perform the flat-card and known-block hardware tests in `docs/TESTING.md`.
2. Tune thresholds from recorded physical evidence and record the first Windows
   hardware-verified baseline.

## Planned after physical validation

- calibrated indexed-turntable capture and multi-view registration;
- confidence/uncertainty stored per point;
- continuous fiducial monitoring for a bumped camera or rig;
- raw frame recording and offline reprocessing;
- optional higher-quality surface reconstruction with explicit hole-fill warnings.
