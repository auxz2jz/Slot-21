# Diagnostic coverage map

This map describes the controls and background work in LaserLine 3D 0.3.0. A
button press is recorded as a request; a separate state/result event or
validated output is required before the operation is treated as successful.

| Feature / trigger | Request and progress evidence | Success evidence | Failure / rejection evidence | Guided check |
|---|---|---|---|---|
| Connect or disconnect camera | requested index, backend, resolution; camera generation; opened details; raw property snapshot | `camera_opened` with actual backend/resolution; `camera_disconnected` or `camera_closed` | `camera_failure`, stop timeout, stale callbacks ignored | Connect, observe live frames, disconnect, reconnect |
| Camera driver settings / refresh | automatic snapshots at open, native settings, background, scan, pause/finish and export; raw values plus property IDs/support caveats | `camera_properties_reported`; appearance/geometric invalidation flags | camera failure, unavailable, or ambiguous zero/unsupported values | Change exposure; refresh; verify background is invalidated; sensor-temperature-only change must not invalidate it |
| Lens calibration | captured-view count and calibration request | saved calibration, accepted views, reprojection error | calibration exception or invalid input | Capture 12+ varied views and calculate |
| Corner calibration and object area | frozen frame, exact six marks, undo/reset, zoom anchor/pan/final view, solve request, fresh object frame, ROI | pose error, landmarks and saved setup | solve/save/load failure | Verify wheel zoom stays under the pointer and left-drag pans without dropping a mark |
| Laser-off background | 15-frame capture request and remaining count; camera snapshot and aggregate frame statistics | background age, resolution, BGR/gray/HSV percentiles, clipping, contrast and sharpness | camera/settings change cancels the capture | Capture with only the laser off; change a relevant camera property and verify recapture is required |
| Laser threshold changes | debounced numeric values for red, dominance, and background difference | live accepted/rejected quality, point counts, saturation and plane residual | auto-suggest rejection or preview exception | Restore defaults, auto-suggest, then make one small change |
| Readiness and scan lifecycle | five-frame readiness history, corner error, support margin, background drift/age, operation ID, state and settings | passed gate or explicit recorded diagnostic override; finish summary | specific reason code, low angle/depth/volume counts, plane inliers/eigenvalues/spans, processing failure, stale generation discard | Start once with stable support, then deliberately force the warning and return to Tune laser |
| Inside/outside green box | per-sample object/left/right/unclassified bounds and spans; candidate pixels inside and outside ROI | bounded per-scan totals and distributions in the finish event/support manifest | missing object/left/right codes and weak/ambiguous support | Compare a tight ROI with an intentionally oversized ROI without accepting unsafe geometry |
| Long no-line interval | consecutive machine-coded no-line count | normal scan continues when the line returns | automatic pause after 50 consecutive unusable-line frames | Remove the line from view until the scan pauses, then retune |
| Point-cloud preview mode | UI mode changes display only | source/project/export colors remain unchanged in automated test | invalid mode rejected | Compare High contrast and Measured surface colors |
| Cleanup and mesh | operation request and source point count | removed-dot count or triangle count | cleanup/mesh exception | Clean a synthetic or physical cloud; create mesh |
| Project save/open and PLY/OBJ/STL export | request plus sanitized destination context | completed write and validated output in automated/self-test | caught file/export exception | Save/reopen `.llscan`; open exports in target software |
| Synthetic self-test | self-test request and deterministic inputs | accepted frames, points, triangles, median depth error, PLY/STL files | `synthetic_demo_failed` / failed CLI report | Press **Run built-in synthetic self-test** |
| Diagnostics ZIP | export request, privacy choice, settings, frame statistics and bounded per-scan evidence | ZIP atomically replaced; manifest and JSONL parse in tests; hard bundle/attachment limits | export failure and skipped/oversized-attachment reasons | Save with and without the optional images; inspect before sharing |
| In-app interaction trace | workflow actions, safe key category/modifiers/target, click/wheel context and canvas actions | ordered event IDs and results | logging errors are swallowed so input is never blocked | Use keyboard navigation, corner zoom/pan/undo and buttons, then inspect the JSONL |
| Application failure | main/thread exception hooks and first-failure marker | normal close event | redacted exception type, message and traceback | Covered automatically; never intentionally crash hardware testing |

## Session and privacy behavior

- Each run has a UUID, ordered event UUIDs, sequence numbers, UTC time,
  monotonic elapsed time, and application version.
- Scan events share one operation ID from start through pause/resume/finish or
  clear.
- The active JSONL has an 8 MiB hard growth limit. Compaction keeps the first
  event/failure, recent failures and exact recent/latest event records, plus
  complete per-event counts. Stored session logs are also limited by count and
  a 48 MiB aggregate budget.
- User-home and working-directory prefixes are redacted before persistence.
  Common API-key/token forms and fields likely to contain typed or clipboard
  text are redacted. In-app key events never read `event.text()` and printable
  keys share one non-identifying category. Nothing outside this application is
  observed.
  Camera images are included only after the user explicitly chooses **Yes**.
  Point clouds are never added to a support ZIP implicitly.
- High-rate laser settings are debounced. Scan detail is sampled at most about
  once per second (plus bounded reason transitions), while complete counts and
  bounded numeric distributions are retained per scan. This replaces the
  150-MB per-frame log observed in the 0.2.0 field test.

## Known diagnostic limitation

Version 0.3.0 still does not contain a persistent in-app multi-step **Test This
Version** wizard or a generated guided-test TXT/JSON report. It records a no-line
watchdog and the decisive evidence needed for the next physical run, but it does
not record raw video unless a future explicit recording feature is added. The
session JSONL and support ZIP remain the evidence source for this candidate.
