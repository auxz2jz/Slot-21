# Field test findings and corrective plan — 2026-10-13

## Status

Evidence review is complete. No scanner code was changed during this review.
Version 0.2.0 is now **USER TESTED / NOT VERIFIED**: it produced usable scan
data, but the tests exposed calibration-interaction, reference-support, camera
evidence, coverage, and diagnostic-retention issues that require a corrective
candidate.

The raw diagnostic archives and camera images remain local because they include
private scene imagery and approximately 150 MB of uncompressed event data per
bundle. This repository stores their hashes and sanitized findings, not the raw
private evidence.

## Evidence identity

| Evidence | SHA-256 |
|---|---|
| `LaserLine3D_diagnostics_20261013_144642.zip` | `B68F71D107486D3AB27F91C7E304DF7719EA081384E6F5C7706F828097D64E8E` |
| `scan.ply` | `59B35A64C6CBB396BFD92845D38BAB9C42EACEB169DBBAED9322702F4A0CF13E` |
| `scan.obj` | `7DE9B59DDC7491D21F52664A71C36C41AB0FC4F36E7C113528FFB3BA552F24F3` |
| `scan.stl` | `BDCC20DC97FA950B5CE51040CEAE87EA51734A378403636290B56A1BDB9E38EF` |
| `LaserLine3D_diagnostics_20261013_145754.zip` | `6F63DE2B18CA193EB7F19A96A9D86E36D8A87EE4857D791E125B8709BC20AF0C` |
| `scan2.ply` | `B5FE84E59203EB8FD1A327ABE1DCD8C12AABF6580031C4AFB97DA70E118DDDCD` |
| `scan2.obj` | `3188BDB531EC1C9A2799CCB29A9656367057FA3B38C77EC5A85B5DBA09B4914A` |
| `scan2.stl` | `3A50BCF3D409CCA10FE1ABFBE5F873D2EE7E940721797BC9ACCF87E7A75F5C4D` |
| `letter_calibration_target_spec.json` | `85F4853389F284EA3A1C1446C93BDB07DEE6A50689125C01D79484521B68A5B4` |
| `Laser_LEFT_Letter_8.5x11.pdf` | `A212E01A503AF8D597BFBE1C984EEECB17DC01EBCF78FD7AC6EDCDDDFCA8371F` |
| `Laser_RIGHT_Letter_8.5x11.pdf` | `28098E94F6FA5A549FA9E33C4B5301384B6B4ECA913B08783546F04236160108` |
| `Photogrammetry_Letter_8.5x11.pdf` | `08CC3400005789CAC02918C523EC60C4FDDBEEF90323A27616FE5FAE9175F919` |

## Test comparison

Both diagnostic ZIPs are cumulative snapshots of the same application session.
The named scan operations and exports distinguish the two final tests.

| Measurement | Test 1: normal lighting | Test 2: adjusted exposure |
|---|---:|---:|
| Accepted frames | 780 / 793 (98.4%) | 437 / 740 (59.1%) |
| Raw profile points | 181,153 | 220,245 |
| Exported PLY points | 135,273 | 181,647 |
| Mesh triangles | 107,288 | 165,494 |
| Median laser saturation | 90.0% | 49.9% |
| Median plane RMS | 0.333 mm | 0.251 mm |
| Median reference support ratio | 0.021566 | 0.003195 |
| Corner-pose reprojection RMS | 3.35 px | 4.60 px |
| Mesh connected components | 1,424 | 1 |
| Mesh boundary edges | 50,908 | 822 |
| 1 mm XZ occupancy | 60.95% | 73.85% |

The second test produced the better geometric result: one connected surface,
far fewer open boundaries and isolated points, higher coverage, and much less
laser clipping. Its darker measured colors can make the model look black in
measured-color mode even though the geometry is better.

## Root-cause findings

1. **Camera-setting evidence is stale.** Both manifests report Exposure `-6`,
   automatic white balance `1`, and white-balance temperature `4600`, but the
   only matching property snapshot occurred about twelve hours before the final
   tests. The laser-off background mean changed from BGR `[158.29, 154.37,
   152.46]` to `[53.03, 45.04, 33.50]`, proving a major camera-output change.
   The current log cannot identify the exact control values that caused it.
2. **The second test lost wall-reference geometry, not object detection.** Its
   object ROI grew from `355 x 575` to `533 x 670` pixels. Median object samples
   rose from 243 to 513, while median left/right wall samples fell from 179/119
   to 53/80. The reference support ratio fell close to the hard `0.003` safety
   guard.
3. **The rejection guard worked correctly.** Test 2 rejected 303 frames: 247
   had nearly collinear/ambiguous reference support, 47 missed the left wall,
   and 9 missed the right wall. Lowering the guard would accept unstable depth
   rather than repair triangulation.
4. **The tuning preview warned before scanning, but start was still allowed.**
   Immediately before test 2, no preview reached `Good`: 128 of 166 were
   ambiguous, 22 missed the right wall, and 16 had no line.
5. **Manual corner marking needs correction.** Zoom is centered on the entire
   image, pan requires right/middle drag, and a left press places a point
   immediately. Therefore an attempted left-drag necessarily adds a landmark.
   Neither landmark edits nor final zoom/pan state are logged.
6. **Missing data has two forms.** Test 1 is highly fragmented and contains
   below-base artifacts. Test 2 has good overall connectivity; its remaining
   holes are more consistent with rejected sweep intervals, surface occlusion,
   or weak laser return than detached static.
7. **The active-session diagnostic log is not size-bounded.** The later bundle
   contains 189,335 events and a 150.45 MB JSONL file. A stale scan ran for about
   9 hours 39 minutes and produced 181,482 per-frame records. The ZIP is only
   about 10 MB, but export and analysis should not require the entire session.

## Legacy target decision

The legacy checkerboard is equivalent to the current 9 x 6-inner-corner,
25 mm-square camera target. It is not a scanning background.

The two laser sheets use eight 28 mm `DICT_4X4_50` ArUco markers with unique
left/right IDs. They are useful prototypes for automatic V-pose calibration,
but should not replace the large matte-white wings unchanged. Black ink can
interrupt the laser witness line, Letter paper is smaller than the current
300 x 400 mm wings, paper curl biases geometry, and the printed dots are not
defined or needed by the documented solver.

Decision: keep the six-point method as a fallback and add an optional
ArUco-assisted method. Prefer a LaserLine3D-specific target with small markers
around the perimeter, scale/seam checks, and broad uninterrupted white laser
witness lanes.

## Corrective implementation plan

### Phase 1 — preserve decisive evidence

- Automatically request and timestamp camera-property snapshots before and
  after native controls, before background capture, at scan start/finish, and
  at diagnostic export.
- Mark unsupported/sentinel driver values and preserve requested versus
  read-back values separately.
- Always record image-derived evidence: BGR/luminance percentiles, black/white
  clipping, laser saturation, background age, and background drift.
- Record landmark add/move/undo/reset, ROI edits, and final zoom/pan state.
- Return structured rejected-frame metrics: attempted support ratio,
  eigenvalues, wall inliers and spans, low-angle counts, depth failures, and
  volume failures.
- Replace unbounded per-frame session logging with per-scan aggregates,
  transition/rejection samples, a bounded detailed ring, size-based rotation,
  and automatic pause after a long no-line interval.

### Phase 2 — make corner marking precise

- Zoom around the cursor or selected landmark instead of the image center.
- Defer point creation until mouse release; treat motion beyond a small
  threshold as pan, so left-drag cannot place a point.
- Keep right/middle pan, add an explicit Mark/Pan mode, draggable existing
  landmarks, Undo, a magnified crosshair inset, and keyboard nudging.
- Show per-point residuals and require an explicit warning/redo when corner-pose
  reprojection error is too high.

### Phase 3 — protect reference geometry before scanning

- Make the object ROI tightly surround only the object and reserve visible
  left/right wall witness zones outside it.
- Display wall span, point count, plane RMS, support ratio, support margin, and
  triangulation angle as live gauges.
- Add a readiness gate: require several consecutive stable `Good` previews or
  require an explicit warned override. Start with a warning margin near twice
  the current support guard, then tune it from new physical data.
- Replace the generic angle message with specific instructions: translate the
  laser line up/down while keeping long segments on both walls; do not pivot it
  toward the hinge or let it leave either wing.

### Phase 4 — expose and reduce missing coverage

- Record accepted and rejected stripe locations so the review page can show a
  coverage heat map and identify missed sweep bands.
- Distinguish low triangulation angle, out-of-depth, out-of-volume, missing-wall,
  weak-object-return, and ambiguous-support failures in the UI and report.
- Keep measured color unchanged in exports, but default low-exposure review to
  high-contrast/neutral display colors with a clear display-only label.

### Phase 5 — optional automatic corner target

- Detect the legacy ArUco IDs as an initial compatibility mode and solve one
  joint two-wall pose from all visible marker corners using robust refinement.
- Validate printed scale, expected IDs, per-marker residuals, wall angle, and
  flatness assumptions; reject partial or inconsistent target layouts.
- Add a project-specific printable target that preserves clear laser witness
  lanes and supports continuous bumped-camera/fixture monitoring.
- Preserve manual six-point calibration when markers are unavailable.

### Phase 6 — export correctness and guided retest

- Report raw-profile, voxelized-cloud, exported-vertex, and face counts with
  unambiguous names; compact unused mesh vertices before OBJ/STL export.
- Add regression tests for anchored zoom, click-versus-drag, ROI/reference
  guards, structured rejection metrics, camera snapshot timing, log rotation,
  target detection, and metadata counts.
- Build a new candidate and repeat two controlled scans with exposure, white
  balance, focus, ROI, calibration, room lighting, and sweep path held constant.

## Exact next action

Implement Phases 1 through 3 first. They directly address the evidence gap,
misplaced landmarks, oversized ROI, and unsafe scan start seen in these tests.
Do not ask for another physical scan until the new candidate records the actual
camera state and refuses or clearly warns on unstable reference geometry.

## Corrective implementation update — 0.3.0 candidate

Phases 1 through 3 reached the software-test gate on 2026-10-13:

- camera properties are sampled automatically at the decisive workflow
  boundaries and now include hue, gamma, backlight, temperature, iris, FourCC,
  buffer, raw values, property IDs, and explicit unavailable/ambiguous-zero
  states;
- full-frame, object-ROI, and outside-ROI aggregate BGR/gray/HSV, clipping, and
  contrast evidence is collected without storing image pixels; spatial
  sharpness is measured for the full frame and rectangular object ROI;
- the active JSONL is capped at 8 MiB and compacted into first/recent/failure/
  latest records plus complete event counts; scan-frame detail is sampled and
  backed by bounded complete per-scan aggregates;
- rejected frames retain machine reason codes, attempted support ratio,
  residual, covariance eigenvalues, wall inliers/spans, normal uncertainty,
  and low-angle/depth/volume rejection-stage counts;
- wheel zoom is pointer-anchored; point placement waits for mouse release; a
  left drag pans without placing a point; right/middle pan, Undo, reset, ROI,
  and final view state are logged;
- scan start requires five recent stable frames, a matching background, the
  recommended support margin, and acceptable corner error, or a clearly logged
  user override; 50 consecutive no-line frames automatically pause capture;
- low-angle guidance now tells the operator to translate the stripe up/down
  while retaining both wall segments rather than pivoting toward the hinge.

The safety thresholds remain unchanged: the 5-degree angle cutoff and 0.003
plane-support guard were not weakened. Draggable existing landmarks, a
magnified crosshair, keyboard nudging, coverage heat maps, ArUco automation,
full-field object triangulation, background point editing, and turntable fusion
remain later work. The 0.3.0 candidate is software tested only until the guided
physical retest in `TESTING.md` passes. At that implementation checkpoint no
0.3.0 field evidence existed; the comparison below updates the state to **USER
TESTED / NOT VERIFIED**.

## Physical comparison update — 0.2.0 versus 0.3.0

Three physical export sets were compared read-only: one 0.2.0 run and two
0.3.0 runs. The original diagnostics and PLY/OBJ/STL files were not modified.

| Evidence | 0.2.0 comparison | 0.3.0 run 1 | 0.3.0 run 2 |
|---|---:|---:|---:|
| Reported exposure | -9 | -7 | -7 |
| Reported auto-WB / temperature | 0 / 4600 K | 1 / 4600 K | 0 / 2800 K |
| Laser-off background mean BGR | 82.84 / 83.19 / 81.05 | 0 / 0 / 0 | 0 / 0 / 0 |
| Exported RGB | median luminance 155; range 41–207 | all points 0 / 0 / 0 | all points 0 / 0 / 0 |
| Accepted / rejected frames | 1,621 / 764 | 1,993 / 651 | 1,604 / 218 |
| Accepted-frame rate | 68.0% | 75.4% | 88.0% |
| Exported points / triangles | 169,315 / 225,754 | 286,308 / 238,697 | 273,913 / 228,322 |
| Median plane RMS | 0.236 mm | 0.251 mm | 0.198 mm |
| Median triangulation angle | 21.6° | 21.1° | 13.7° |
| Corner-pose reprojection error | 2.86 px | 3.79 px | 3.43 px |
| Nearest-neighbour distance p95 | 1.026 mm | 0.986 mm | 1.001 mm |
| Points with nearest neighbour >1 mm | 6.95% | 4.14% | 5.03% |

### Confirmed cause of the black models

This is not a geometry failure and is not merely a viewer illusion. Both 0.3.0
PLY files store RGB `(0, 0, 0)` for 100% of their points; their OBJ vertex
colors originate from the same cloud. STL carries no color. Both diagnostic
bundles contain an exactly black laser-off background, although their current
camera frames are not black. The reconstruction code uses the laser-off
background as the point-color source so the live red stripe is not baked into
the surface. Consequently an all-black detection background creates all-black
saved point colors.

The camera did respond to white balance: the two current-frame channel means
differ. It did not affect the saved model because both selected background
images were already zero in every channel. Exposure is not the primary cause
either: the visible 0.2.0 model used a darker reported exposure (-9) but an
illuminated background image. The relevant color sampling and high-contrast
preview code is unchanged between the inspected 0.2.0 and 0.3.0 checkpoints.
No preview-mode change was recorded in either 0.3.0 session.

### Geometry and reflection findings

- The 0.3.0 runs accepted a larger fraction of frames and produced more points.
  Their local nearest-neighbour statistics are at least as clean as 0.2.0 and
  contain fewer >1 mm local gaps, consistent with the user's report of fewer
  stray dots.
- Run 2 had the strongest plane fit and fewest rejected frames, although its
  lower median triangulation angle provides less depth leverage than the other
  two runs. Keep the 5-degree safety cutoff and 0.003 support guard unchanged.
- Diagnostics observed about 908 and 901 candidate laser pixels per frame
  outside the green ROI in the two 0.3.0 runs. Those observations confirm that
  reflections/background responses still exist, but the current reconstruction
  triangulates only the object segment inside the ROI. The evidence does not
  support attributing a particular exported point to a board reflection.
- The same lens calibration was used, but the 0.3.0 corner-pose residuals were
  higher. Without a dimensioned ground-truth object, absolute accuracy and the
  user's perceived corner sharpness cannot be proven numerically. Visible gray
  variation in 0.2.0 also made surface detail easier to see than all-black RGB.

### Recommended correction — not yet implemented

1. Keep the 0.3.0 laser detection, ROI filtering, evidence collection, and
   geometry safety thresholds.
2. Separate the **laser-off detection background** from a **surface-color
   reference**. The dark image can remain valid for subtraction, while a second
   laser-off image with useful illumination supplies RGB after geometry capture.
3. Reject or warn on an unusable color reference (for example, all pixels near
   black). If no usable color image exists, assign an explicit neutral gray for
   review/export rather than silently writing black RGB.
4. Make neutral/high-contrast geometry shading explicit on both Scan and Review
   pages, log the active mode at finish/export, and offer measured versus neutral
   color export without changing coordinates.
5. Repeat the corner marking until reprojection error is preferably 2 px or
   lower, then run a controlled A/B scan with camera, object, ROI, lighting, and
   sweep held fixed. Capture surface color with the laser off only after the
   geometry sweep, without moving the camera or object.
