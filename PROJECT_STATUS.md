# Project status and verified baselines

## Scope

This is an independent Windows project for hand-swept red laser-line 3D
scanning. It does not use or modify the separate photogrammetry project.

## Discussion backlog (not an active task)

Future feature ideas and user scan observations are recorded in
[docs/IDEAS_BACKLOG.md](docs/IDEAS_BACKLOG.md). These notes are not authorization
to implement new work. Finish the current approved task before considering them.

## Recent discussion memory (2026-10-14) — NOT current work

The detailed discussion record is in **docs/IDEAS_BACKLOG.md, Sections A–S**.
It includes the separate laser-off detection versus well-lit color/texture photo,
complete per-test-run ZIP exports, higher-resolution camera/point cloud, laser
subpixel detail and camera-assisted manual laser focusing, reflective Creality
3 mm dots, printed ArUco/AprilTag markers, marker-based moving-camera alignment,
and eventual wide-reference + close-detail two-camera reconstruction.

**User's current preference:** investigate automatic **ArUco/AprilTag marker
recognition** on both measured V walls first (potentially complemented by
random 3 mm Creality dots) so camera repositioning might no longer require
manual visibility of all six corner landmark points. A closer camera could
provide more object pixels, but **cannot reliably reconstruct a freely swept
laser line unless the system still determines its laser plane per frame**.
Current code needs laser stripe support on **both reference walls**; tracking
markers alone do not replace those stripes. Therefore retain the **two-camera
alternative**: a wider view to measure the wall stripes/laser plane and a
separately calibrated close-up view for object detail, with synchronized
observations, common coordinates and known-object validation. Marker recognition
requires sufficient visible, sharply imaged markers in measured fixture
positions; it cannot promise all angles or distances. Current scanner is
single fixed-camera, manual six-point calibration.

**Priority confirmed (2026-10-14):** reduce and quantify depth noise on the *existing Slot-21 laser-line scanner* before exploring new LiDAR or stereo hardware. Preserve ideas for repeated rotating-LiDAR sampling, dual capture reference images, and optional real-time surface preview as future experiments. Work from a flat-target scan with raw-vs-cleaned-vs-meshed residual metrics; see Ideas Backlog Sections P and R. This note does not authorize code changes or interrupt current Codex work.

**Second camera vs. laser grid (2026-10-14):** explored adding a second stationary stereo camera to the existing V-corner/hand-swept stripe scanner for geometry cross-checks and depth-noise rejection, while keeping the manual one-laser sweep; a static or moving grid needs stripe identification and separate laser-plane calibration and does not inherently reduce noise. Details in Ideas Backlog Section S. No code changes approved.

**Handheld stereo prototype preference (2026-10-14):** user prefers a rigid, twin ~8 MP USB-camera and fixed focusable laser scanning head **tethered to their existing Windows laptop**, avoiding Raspberry Pi/Jetson/battery expense initially. Miniature ToF ranging is optional distance guidance; the first prototype needs individual/stereo/laser calibration and a way to register handheld motion (ArUco/AprilTag pose or validated feature tracking). Retain the original Slot-21 fixed-camera V-reference baseline. Details in Ideas Backlog Section O.

These are durable **future research ideas only**, not an approved implementation.
Do not expand or interrupt the current approved Codex task or weaken existing
geometry/recovery/diagnostic checks. Consult the scoped relevant sections
of the ideas backlog only when planning user-approved features.

## Atomic-task roadmap and checkpoints — 2026-10-15

**Canonical instructions:** [AGENTS.md](AGENTS.md) routes to the [Master Instruction Library](https://github.com/auxz2jz/master-instruction-library), particularly Core Recovery Section 16 and Codex Usage Efficiency Sections 20–26. These rules apply without being copied here. **Canonical current-state handoff:** [docs/CODEX_HANDOFF.md](docs/CODEX_HANDOFF.md). The queue below is the existing project's compact roadmap; do not create a parallel task registry.

**Scope and verified-state protection:** Published **v0.4.0 remains software-tested and physically exercised, but full guided/accuracy verification is pending**. The user explicitly authorized new Arducam/high-resolution camera-mode and profile development on 2026-10-20; the source tree is now an unreleased **v0.5.0 development candidate**, not a published or user-verified replacement. Earlier v0.2.0 was user-tested, but the repository does not establish a **user-confirmed working/accuracy-verified version**; do not invent one. Preserve exact v0.4.0 source checkpoint `2e3cc262e69633894c55c61966302f940185dc2a` and its package/hash data below. Initial remote `main` before the atomic workflow change was `d8b63d81e633b206a9a9f3fa89b023dc47b10a4d`. GitHub remote state does **not** prove another machine's uncommitted state; inspect local Git before editing.

Tasks below describe the next **existing authorized testing/recovery path**; items explicitly requiring hardware evidence or new development authorization must not be started automatically. All are bounded; break down any unexpectedly large task before working it. For every task record inputs/files, expected result, measurable completion, verification, backup, and next model setting in `docs/CODEX_HANDOFF.md`.

- **S21-AT-001 — DONE (documentation-only; GitHub readback verified 2026-10-15).** Objective: adopt the global atomic development workflow without duplicating master rules. Inputs: master index/core/usage standards, prior handoff, status, testing, Git remote history. Files: root `AGENTS.md`, this status/queue, `docs/CODEX_HANDOFF.md`, recovery/storage documentation if stale. Output: durable instructions, queue, accurate handoff. **Done when:** those files exist on remote `main`, are cross-linked, preserve v0.4.0 baseline, and repository readback verifies requested fields. **Verify:** fetch committed files and check required sections and unchanged scanner source; no runtime build for documentation-only change. **Setting:** Low/Medium reasoning.
- **S21-AT-002 — DONE (local checkout reconciled 2026-10-15).** Objective: inspect local `git status --short --branch`, reconcile local vs `origin/main`, and inventory protected local release ZIPs, raw scans, private diagnostics/calibrations **without uploading them**. Result: the actual Windows checkout was clean, was safely fast-forwarded through documentation-only commits to remote `main`, and the two supplied complete-run ZIPs plus the published v0.4.0 artifacts remained local/ignored and unmodified. No reset, clean, deletion, source edit, or private upload occurred. **Verify:** local branch/status/head and SHA-256/manifest checks. **Setting:** Low/Medium.
- **S21-AT-003 — IN PROGRESS; first v0.4.0 physical bundles analyzed 2026-10-15.** Objective: run the existing v0.4.0 controlled hardware guide in `docs/TESTING.md` as smaller checkable segments (camera and calibration readiness, laser/reference readiness, scan/review/package). The two bottle runs prove real camera/calibration/scan/review/export/complete-ZIP operation and are summarized below, but they do not record every guided-test step and do not establish dimensional accuracy. Depends on S21-AT-002 and actual camera/V/laser. Files: guided test results and private local test diagnostics; source unchanged. **Done when:** remaining test steps, errors, and opt-in run evidence are recorded accurately; **verify:** observed device behavior, not a synthetic PASS. **Setting:** Medium for interpreting diagnostics.
- **S21-AT-004 — PARTIAL / REPEAT REQUIRED after 2026-10-17 smaller-target attempt.** Objective: one reproducible matte-flat-object laser sweep with unchanged optics/lighting and a complete-run ZIP. The smaller target materially improved two-wall support and produced a much flatter isolated target cloud, but the corner solve remained `9.45 px` and both scan attempts again started through readiness overrides. The package omitted scene images, so target size/material/placement cannot be visually confirmed. Preserve it as promising but provisional evidence, not an accuracy baseline. **Done when:** a smaller-target run starts only after five stable Good previews, without override, with practical corner error near the recommended `≤2 px`; **verify:** bundle manifest, opted-in scene image and usable raw target points. **Setting:** Medium.
- **S21-AT-005 — PARTIAL / PROVISIONAL; final diagnosis blocked by repeated S21-AT-004.** Objective: quantify signed point-to-best-fit-plane deviations (RMS, MAD, p95/p99), profile banding vs spikes, raw/cleaned/mesh differences; do not equate pixel density with accuracy. The isolated 2026-10-17 target is substantially flatter than the confounded large-board attempt, but the `9.45 px` pose error prevents attributing the remaining approximately `1 mm` RMS to scanner depth noise. **Done when:** the same reproducible calculation is applied to an accepted, no-override smaller-target run and suspected error sources are recorded with uncertainty. **Setting:** High reasoning if geometric interpretation is difficult; otherwise Medium.
- **S21-AT-006 — DEFERRED, requires measured evidence and explicit development authorization.** Objective: choose one minimal, reversible depth-noise correction with targeted tests and original raw-cloud preservation. Inputs: S21-AT-005 findings and fresh authorization; files only those implicated by evidence. **Done when:** user-approved patch, relevant regression tests, checkpoint and handoff are verified; do **not** assume this task is approved today. **Setting:** High for nontrivial geometry; Medium for bounded filtering.
- **S21-CAM-001 — DONE / SOFTWARE-TESTED 2026-10-20; B029201 HARDWARE TEST PENDING.** Objective: support the new Arducam B029201 and other high-resolution UVC cameras without guessing that a requested mode was accepted. Result: v0.5.0 source offers presets through 3840 × 2160 (including B029201 2592 × 1944 and 3264 × 2448), requested 1–120 fps, MJPEG/YUY2/default transport, format-first negotiation, actual resolution/FPS/FourCC read-back, explicit substituted/unverified warnings, and `camera_mode_negotiated` evidence. Verification: 11 targeted camera tests, full 101-test suite, deterministic self-test and v0.5.0 Qt smoke passed. No executable/package was built and no physical high-resolution mode is claimed verified. **Setting:** Medium reasoning.
- **S21-CAM-002 — AUTHORIZED / PENDING S21-CAM-001.** Objective: add in-program camera-control profiles while preserving **Camera driver settings…** as the compatibility fallback. Expected output: explicit supported-property apply/read-back, named JSON save/load, failure/mismatch reporting, geometry/background invalidation, diagnostics, privacy-safe export evidence, and guided tests. Do not invent generic ranges or claim unsupported controls; the camera/driver remains authoritative. **Done when:** profile round-trip and apply/read-back tests pass and the B029201 physical test confirms which controls it honors. **Setting:** High reasoning for driver-state/invalidation integration; reduce to Medium for documentation/build work.

**Cadence and halt gates:** checkpoint after each verified task, before risky/expensive work, and periodically during long sessions; never upload secrets or user diagnostic content. When **usage telemetry is unknown**, do not invent a percentage; end after at most two small tasks or one expensive task, save the handoff, and stop before a costly follow-up. Complete and verify the authorized camera-profile task before packaging; afterward, B029201 mode/control behavior and the corrected corner calibration require physical evidence. Incomplete work stays PARTIAL/BLOCKED, never VERIFIED.

## v0.5.0 camera-mode development checkpoint — 2026-10-20

The user replaced the Logitech camera with an Arducam B029201 8MP IMX219 UVC
camera and authorized higher resolution/frame-rate support plus integrated camera
profiles. `S21-CAM-001` is complete in source: the camera page now includes
640 × 480 through 3840 × 2160 presets, including the B029201's published
2592 × 1944 and 3264 × 2448 streaming modes; requested frame rates span 1–120;
and users can request MJPEG, YUY2, or the driver default. The worker applies
FourCC before dimensions/FPS so USB 2.0 high-resolution MJPEG modes have a fair
chance to negotiate, then reads back actual width, height, FPS and FourCC.

The UI warns when the backend substitutes a mode or leaves FPS/FourCC unreported.
Diagnostics separately preserve the request, individual property-set returns,
actual values, mismatches/unverified fields, and final accepted/substituted/
unverified outcome in `camera_mode_negotiated`; no request alone is treated as
proof. Existing calibration/background invalidation behavior is preserved.

Verification passed: targeted camera/UI tests `11 passed`; full suite `101
passed`; deterministic synthetic self-test passed with 24 accepted frames, 4,316
points, 8,334 triangles and 1.4491 mm median synthetic depth error; v0.5.0 Qt
smoke passed with seven workflow pages and both printables. This is a
**software-tested development candidate only**. No 0.5.0 Windows package exists,
and the B029201 must physically prove each mode because OpenCV cannot reliably
enumerate all UVC capabilities in advance.

Next exact task is `S21-CAM-002`: explicit in-app camera-property controls and
named JSON profiles with apply/read-back mismatch evidence, while retaining the
native driver dialog. Focus/autofocus/zoom changes must invalidate both geometric
calibrations; exposure/gain/color changes must invalidate the laser background;
unsupported or refused properties must remain visible rather than silently
claimed applied.

## v0.4.0 physical evidence comparison — 2026-10-15

Two private complete-run bundles from the same physical bottle setup were
analyzed locally and left unmodified. ZIP CRC checks and every manifest size and
SHA-256 entry passed; both bundles contain the canonical raw/final PLY, final
OBJ/STL and sidecars, calibration, editable project and opted-in images. No
private bundle, image, point cloud, calibration, path or run identifier was
uploaded to GitHub.

- Both runs used the same byte-identical camera/corner calibrations, 1920 × 1080
  DirectShow stream, reported exposure `-7`, white balance `2800`, object ROI,
  Fine `0.50 mm` voxel preset and `80 ms` capture interval. The corner-pose
  reprojection residual was `4.67 px`, above the recommended `2.00 px` and still
  an accuracy concern.
- Run 1 mixed three different background/tune/scan phases into one cloud. Its
  last laser-off background was exactly black, its bounded log had 2,418 dropped
  old records after an almost twelve-hour run, and 38 sequential cleanup actions
  reduced 407,424 raw fused points to 225,193. It accepted 1,508/1,837 frames
  (`82.09%`). Because lighting/tuning changed inside the run, its final settings
  cannot explain the whole fused model.
- Run 2 used one valid dim laser-off background, one tune and one scan; no log
  records were dropped. It accepted 2,183/2,491 frames (`87.64%`), reduced
  no-laser rejects from `5.01%` to `1.93%` and shallow-angle rejects from `6.10%`
  to `3.69%`, and retained 359,407 of 486,944 raw fused points after 15 cleanup
  actions. This is the cleaner, more interpretable workflow baseline.
- Final local nearest-neighbour medians were nearly identical (`0.366 mm` Run 1,
  `0.368 mm` Run 2). Run 2's higher count is therefore mainly more coverage and
  less repeated cleanup, not proof of finer camera detail or greater dimensional
  accuracy. On the overlapping final surfaces, Run 1→Run 2 nearest distance had
  `0.333 mm` median and `94.3%` within `1 mm`; the asymmetric Run 2→Run 1 result
  reflects Run 2's extra retained coverage. This is repeatability evidence only.
- The Run 1 final PLY contains `11.84%` exactly black vertices because part of
  the fused acquisition followed the all-black background; Run 2 contains only
  `0.036%`. Reported camera controls were unchanged, so the color difference is
  attributable to captured scene/background and lighting history, not white
  balance or geometry corruption. Both exports otherwise contain real RGB; OBJ
  vertex colors are optional viewer extensions and STL intentionally has no
  color.
- Both scans show the curved spray bottle plus background admitted by the tall
  rectangular ROI, horizontal sweep banding, and an intentionally open
  single-view surface. Neither is a controlled flat-target measurement, so
  object-plane RMS/MAD/p95/p99 depth noise and absolute accuracy cannot be
  inferred. The recorded ~`0.39 mm` per-frame RMS is laser-plane fit residual,
  not scanned-object surface error.

Evidence-based next step: one short run of a rigid matte flat target, with fixed
camera/object/lighting, a tighter object-only ROI, one valid non-black laser-off
capture, one auto-tune, one uninterrupted slow sweep, and no repeated cleanup
before packaging the raw cloud. Only that evidence can unblock S21-AT-004/005.

## v0.4.0 flat-target attempt — 2026-10-16

Two new private complete-run bundles and their separately exported models were
analyzed locally and left unmodified. Both ZIPs passed CRC plus every manifest
size/SHA-256 check; the separate PLY/OBJ/STL files are byte-identical to their
corresponding manual-export entries inside the bundles. No private artifact was
uploaded. The Master Instruction Library and Slot-21 remote instructions were
unchanged at the start of this task.

The target is a large matte flat board standing in front of the calibrated V.
It nearly fills the available width and height. The green ROIs occupy about
`45%` of the image width and `70–78%` of its height, leaving relatively short
laser witness segments on the reference walls. More decisively, both bundles
use the same `10.86 px` corner-pose reprojection error versus the recommended
`≤2.00 px`, and both scan starts explicitly overrode a not-ready state. The
first override followed no detected line; the second followed missing left-wall
support. These conditions invalidate an accuracy baseline even though many
frames were later accepted.

- **Standard (`0.75 mm`) run:** 415/722 frames accepted (`57.5%`); 204,009 raw
  and 197,982 once-cleaned points. Degenerate reference support caused 206
  rejects (`28.5%`). Median wall spans across sampled frames were about `62 mm`
  left and only `32 mm` right; the median plane-support ratio was `0.0045`.
- **Fine (`0.50 mm`) run:** 448/623 frames accepted (`71.9%`); 287,613 raw and
  281,553 once-cleaned points. Degenerate support still caused 72 rejects
  (`11.6%`). Median wall spans improved to about `66 mm` left / `57 mm` right
  and support ratio `0.0059`, close to but not consistently above the recommended
  `0.006` margin.
- Fine retained about `42%` more final points and reduced local median spacing
  from `0.613 mm` to `0.427 mm`, as expected from the voxel setting. It did not
  materially improve measured flatness, so density must not be called accuracy.
- On the central 80% of the detected target, after excluding obvious background
  and fitting a best-fit plane, raw Standard/Fine RMS deviations were
  `3.95/3.76 mm`, MAD `1.39/1.46 mm`, absolute p95 `9.11/7.64 mm`, and absolute
  p99 `15.38/12.77 mm`. One cleanup pass reduced tail RMS to `3.37/3.28 mm` and
  p95 to `7.67/6.89 mm`, but core MAD stayed near `1.4 mm`.
- Residual maps contain strong horizontal sweep bands. Raw median residual by
  vertical position varied with about `0.77/0.73 mm` RMS and `3.92/3.01 mm`
  peak-to-peak, versus only `0.34/0.20 mm` RMS across horizontal position.
  Cleanup removes isolated tails but not this structured banding.

These values prove that the current result is not acceptably planar, but cannot
separate scanner noise from the `10.86 px` pose error, limited/degenerate wall
support, possible target bow, and the readiness overrides. The target was indeed
too large for a clean reference-wall test. Repeat with a rigid letter-size
(`216 × 279 mm`) or smaller board in portrait orientation, leaving substantial
wall area on both sides. Remove it for corner calibration; frame all six V
landmarks with margin; verify the physical V dimensions/90° angle; and do not
scan until error is much lower, both wall spans are preferably `80–100+ mm`,
support ratio is at least `0.006`, and five previews are Good. Use Standard first;
Fine can follow as a separate A/B run only after the Standard run is accepted.

## v0.4.0 smaller-target repeat — 2026-10-17

One new private complete-run bundle and twelve separately supplied export files
were analyzed locally and left unmodified. The ZIP passed CRC and every manifest
size/SHA-256 check (`27` included, `0` missing, `2` intentionally omitted); all
twelve separate PLY/OBJ/STL and sidecar files are byte-identical to the matching
manual-export entries. The package is complete, has no dropped diagnostic
records or artifact failures, and intentionally contains no private scene image.
The Master Instruction Library and Slot-21 remote instructions were unchanged.

This test run contains two attempts. A short Standard (`0.75 mm`) attempt was
finished and then cleared: 168/257 frames accepted (`65.4%`), 56,117 points,
median support ratio `0.0281`, and one degenerate-support reject. No cloud from
that cleared attempt is retained in the bundle. The saved Fine (`0.50 mm`)
attempt accepted 697/870 frames (`80.1%`), fused 247,663 raw points and retained
239,714 after one cleanup pass removed 7,949 (`3.2%`). Its median support ratio
was `0.0276` (p05 `0.0185`), and only 7/870 frames (`0.8%`) failed for degenerate
support. This is a major reference-support improvement over the 2026-10-16 Fine
attempt (`0.0059` median support and `11.6%` degenerate rejects), consistent with
the smaller target leaving more wall visible.

However, both attempts again used **Start anyway** while the latest preview had
no detected laser, zero consecutive Good frames, and no measured support margin.
The corner-pose error improved only from `10.86 px` to `9.45 px`, still far above
the recommended `≤2 px`. The saved attempt also ended with the 50-no-line safety
pause. These are workflow/calibration failures even though most later frames had
strong support.

For provisional flatness measurement, disconnected reconstructed wall strips
were separated from the obvious broad central target using the clear X-axis
gaps, then the central 80% of that target was fit to a plane. The raw central
target contained 63,116 points: RMS `1.059 mm`, MAD `0.664 mm`, absolute p95
`2.009 mm`, p99 `2.976 mm`, and `71.9%/94.9%` within `1/2 mm`. After one cleanup,
62,650 central points remained: RMS `0.982 mm`, MAD `0.662 mm`, p95 `1.956 mm`,
p99 `2.786 mm`, and `72.2%/95.3%` within `1/2 mm`. Median-profile variation was
about `0.244 mm` RMS vertically (`1.14 mm` peak-to-peak) and `0.065 mm` RMS
horizontally (`0.27 mm` peak-to-peak) before cleanup. Median nearest-neighbour
spacing was `0.518 mm`, matching Fine density; cloud median luminance was `51.89`
and fewer than `0.05%` of points were exact black.

The smaller target therefore solved the principal wall-support problem and the
isolated plane is encouragingly flatter. It does **not** complete accuracy
verification: scene geometry was not photographed, the extraction differs from
the prior large-board measurement because disconnected wall strips had to be
removed, and `9.45 px` pose error can still create systematic depth bias. The
next bounded step is corner calibration only: empty V, laser off, actual measured
equal wing width/inside angle/top-to-bottom mark separation, exact six-point
order, and careful zoom/pan placement until the solve is near `≤2 px`. Do not run
another full scan until that gate is met; then repeat one Standard scan without
overriding readiness and opt in to the scene image for setup verification.

## Recovery checkpoint — 2026-10-14

- **Latest candidate:** 0.4.0, **SOFTWARE TESTED / PHYSICALLY EXERCISED / FULL
  GUIDED AND ACCURACY VERIFICATION STILL REQUIRED**. Two physical bottle runs
  validate the complete-run workflow and provide comparative scan evidence, but
  not the required flat-target dimensional/depth-noise measurement.
- **Last user field evidence:** one 0.2.0 comparison and four 0.3.0 scan exports
  were reviewed. Geometry remained present; an object-in-place illuminated
  laser-off background restored measured color. Details are in
  `docs/FIELD_TEST_2026-10-13.md` and the analysis below.
- **Completed task:** 0.4.0 adds isolated physical-test runs, one final evidence
  ZIP, conservative density/preview choices, and the cleanup/second-Finish fix.
  Photo texturing and the other ideas in `docs/IDEAS_BACKLOG.md` remain deferred.
- **Durable repository:** `https://github.com/auxz2jz/Slot-21`, branch `main`.
  The 0.4.0 implementation checkpoint is
  `2e3cc262e69633894c55c61966302f940185dc2a`.
- **Private evidence:** raw camera images, diagnostic archives, calibrations,
  scans, environments, and Windows binaries remain local and outside normal
  Git history. No user scan or diagnostic file was deleted.

## 0.4.0 completed scope

Known-good starting point is the published 0.3.0 source commit
`43ff46e438e73441db0519e7e30b2bc437c36d5d`; the documentation checkpoint at
the start of this work is `34e72e3`. Git was clean and synchronized before
modification.

Newest physical evidence adds two illuminated 0.3.0 runs. `scan4.1` retained
312,389 cleaned points with approximately 0.634 mm median nearest-neighbour
spacing. Its object-in-place, laser-off frame restored measured surface color.
The earlier `scan3` laser-off frame did not contain the object, so its non-black
colors came from the lit fixture/background rather than the object itself.
Corner-pose reprojection remained 3.43 px, so added density must not be described
as added dimensional accuracy.

Implemented and verified scope:

1. Explicit per-test-run identity and bounded run-scoped diagnostic events.
2. A separate, opt-in complete-run ZIP that streams and validates PLY, OBJ,
   STL, matching JSON sidecars, project data, settings, diagnostics, hashes,
   and optional user-approved camera/background images. Keep the compact support
   ZIP and its privacy/size limits unchanged.
3. Conservative Standard/Fine scan-density presets and visible counts for
   acquired, fused/exported, and previewed points. Preserve geometry safety
   thresholds and the two-million raw-point guard.
4. A repeated Finish action no longer restores a cloud that the
   user already cleaned.
5. Raw fused data are preserved before cleanup; package retries are recorded;
   partial archives identify missing files honestly; ZIP publication is atomic,
   hashed, single-pass validated, free-space checked, and cancellable.
6. Back-to-back runs preserve reusable calibration/background, clear prior scan
   evidence, and warn before unsaved evidence is replaced or the app is closed.

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

## Physical 0.3.0 comparison — 2026-10-13 evening

The two 0.3.0 PLY exports contain valid coordinates but RGB `(0, 0, 0)` for
every point. Their saved laser-off backgrounds are also exactly black. The
reconstructor intentionally samples point RGB from the laser-off background to
avoid painting the red stripe onto the object, so the black exports follow
directly from that color source. The 0.2.0 comparison background averaged about
BGR 83/83/81 and its exported point colors had median luminance about 155.

Exposure and white balance are not the primary cause. The 0.2.0 scan reported
exposure -9 yet retained visible gray colors; both 0.3.0 scans reported exposure
-7. The 0.3.0 tests reported different white-balance states (automatic at 4600
K versus manual/zero-or-unsupported at 2800 K), but both selected an all-zero
background as the RGB source. White balance cannot recover zero-valued pixels.
The relevant background-color sampling and point-preview lifting logic did not
change between the 0.2.0 and 0.3.0 source checkpoints.

Geometry evidence supports keeping the 0.3.0 detection work. Accepted-frame
rates were approximately 68.0% for 0.2.0, 75.4% for the first 0.3.0 run, and
88.0% for the second 0.3.0 run. Exported point counts were 169,315, 286,308,
and 273,913 respectively. The percentage of points whose nearest neighbour was
farther than 1 mm fell from 6.95% to 4.14% and 5.03%, consistent with the
reported cleaner clouds. Absolute dimensional accuracy cannot be established
without ground truth, and the 0.3.0 corner-pose reprojection errors (3.79 px and
3.43 px) were worse than the 0.2.0 comparison (2.86 px), so calibration should
be tightened before claiming sharper or more accurate geometry.

## Software-tested 0.4.0 candidate baseline

Build date: 2026-10-14 (America/Los_Angeles).

- Python 3.12.14
- NumPy 2.5.3
- OpenCV 4.14.0.94 (headless runtime)
- SciPy 1.18.1
- PySide6 Essentials / Qt 6.12.0
- PyInstaller 6.22.3 with hooks 2026.8
- final build pipeline: 97/97 automated tests passed in 8.33 seconds
- final coverage gate: 97/97 tests passed; 81.42% statement coverage with
  75% required
- source/prebuild and packaged scan/export self-tests passed: 24/28 frames
  accepted, 4,316 fused points, 8,334 triangles, 1.4491 mm median synthetic
  depth error
- packaged Qt smoke passed: application version 0.4.0, real seven-page window,
  Qt 6.12.0, both printables present
- required `_internal/cv2/config.py` and `config-3.py` are present
- published folder: `dist/LaserLine3D_0.4.0`
- package: 346 files, 311,338,437 bytes
- release ZIP:
  `output/windows/LaserLine3D_Windows_0.4.0_2026-10-14.zip`
- ZIP: 361 entries, 123,391,819 bytes; every entry passed decompression/CRC,
  the archive has one `LaserLine3D_0.4.0` top-level folder, and the required
  EXE/OpenCV configuration files are present
- executable SHA-256:
  `C0144B206778C46974A1947EB4BAADD1AFBBE990966CE93519185F017A4041D7`
- release ZIP SHA-256:
  `52B195DD3EECC77B3C1B0DF030CE29FD5E528EAA671FE110982414C50750B356`
- the executable embedded in the ZIP has the same SHA-256 as the published EXE
- maintainable-source implementation checkpoint:
  `2e3cc262e69633894c55c61966302f940185dc2a`

This is a software-tested candidate, not a hardware-accuracy claim. The final
diff received an independent focused review with no release-blocking findings.
Very large canonical OBJ/STL/project staging is still synchronous; ZIP writing
and validation report progress and can be cancelled safely.

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
- There is no persistent in-app guided-test wizard or generated prose test
  report. The toolbar run boundary, structured complete-run ZIP, and documented
  procedure are the current evidence path.
- Very large OBJ/STL/`.llscan` generation can temporarily pause UI updates for
  that individual file; archive writing/validation itself is progress-reported
  and cancellable.
- Clean-PC packaging has not yet been independently tested on a second Windows
  machine, and physical measurement accuracy remains unverified.

## Next validation gate

1. Extract the 0.4.0 ZIP into a fresh directory; never merge `_internal` files.
2. Follow every step in `docs/TESTING.md`, including anchored zoom/pan,
   Standard then Fine density, preview counts, readiness return/override,
   repeated-Finish cleanup, and diagnostics privacy checks.
3. Repeat controlled flat-card, known-block, and object scans with locked
   camera controls and unchanged lighting/fixture/ROI.
4. Make **Finish test & save complete ZIP…** the last action for each run; upload
   that single ZIP for comparison and start a new run before changing setup.
5. Record a Windows hardware-verified baseline only if the physical checks and
   known-dimension measurements pass.
