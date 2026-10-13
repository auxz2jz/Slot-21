# Diagnostic coverage map

This map describes the controls and background work that exist in LaserLine 3D
0.2.0. A button press is recorded as a request; a separate state/result event or
validated output is required before the operation is treated as successful.

| Feature / trigger | Request and progress evidence | Success evidence | Failure / rejection evidence | Guided check |
|---|---|---|---|---|
| Connect or disconnect camera | requested index, backend, resolution; camera generation; opened details; raw property snapshot | `camera_opened` with actual backend/resolution; `camera_disconnected` or `camera_closed` | `camera_failure`, stop timeout, stale callbacks ignored | Connect, observe live frames, disconnect, reconnect |
| Camera driver settings / refresh | settings-dialog request; before/after raw properties | `camera_properties_reported`; invalidation flags | camera failure or unsupported/raw values | Change exposure; refresh; verify background is invalidated |
| Lens calibration | captured-view count and calibration request | saved calibration, accepted views, reprojection error | calibration exception or invalid input | Capture 12+ varied views and calculate |
| Corner calibration and object area | frozen frame, six marks, solve request, fresh object frame, ROI | pose error and saved setup | solve/save/load failure | Solve an empty V, then capture and box the object |
| Laser-off background | 15-frame capture request and remaining count | background resolution and channel statistics | camera/settings change cancels the capture | Capture with only the laser off; change a camera property and verify recapture is required |
| Laser threshold changes | debounced numeric values for red, dominance, and background difference | live accepted/rejected quality, point counts, saturation and plane residual | auto-suggest rejection or preview exception | Restore defaults, auto-suggest, then make one small change |
| Start, pause, resume, finish, clear scan | scan operation ID, state, settings, processed-frame count | accepted/rejected counts, points, finish result | per-frame rejection reason, processing failure, worker timeout, stale generation discard | Run one stationary sweep; pause/resume without moving the object; finish; clear |
| Point-cloud preview mode | UI mode changes display only | source/project/export colors remain unchanged in automated test | invalid mode rejected | Compare High contrast and Measured surface colors |
| Cleanup and mesh | operation request and source point count | removed-dot count or triangle count | cleanup/mesh exception | Clean a synthetic or physical cloud; create mesh |
| Project save/open and PLY/OBJ/STL export | request plus sanitized destination context | completed write and validated output in automated/self-test | caught file/export exception | Save/reopen `.llscan`; open exports in target software |
| Synthetic self-test | self-test request and deterministic inputs | accepted frames, points, triangles, median depth error, PLY/STL files | `synthetic_demo_failed` / failed CLI report | Press **Run built-in synthetic self-test** |
| Diagnostics ZIP | export request, privacy choice, settings and session metadata | ZIP atomically replaced; manifest and JSONL parse in tests | export failure and skipped-attachment reasons | Save with and without the optional images; inspect before sharing |
| Application failure | main/thread exception hooks and first-failure marker | normal close event | redacted exception type, message and traceback | Covered automatically; never intentionally crash hardware testing |

## Session and privacy behavior

- Each run has a UUID, ordered event UUIDs, sequence numbers, UTC time,
  monotonic elapsed time, and application version.
- Scan events share one operation ID from start through pause/resume/finish or
  clear.
- The newest 20 session logs are retained; each session keeps a bounded recent
  in-memory event window.
- User-home and working-directory prefixes are redacted before persistence.
  Camera images are included only after the user explicitly chooses **Yes**.
  Point clouds are never added to a support ZIP implicitly.
- High-rate laser settings are debounced. Per-frame scan events are retained
  because their rejection reasons are the primary evidence for noisy scans.

## Known diagnostic limitation

Version 0.2.0 provides a documented guided hardware procedure and structured
support bundle, but it does not yet contain a persistent in-app multi-step
**Test This Version** wizard, automatic stall watchdog, or generated guided-test
TXT/JSON report. Those items remain planned after the first 0.2.0 physical
validation; the session JSONL and support ZIP are the evidence source for this
candidate.
