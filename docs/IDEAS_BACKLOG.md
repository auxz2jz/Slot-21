# LaserLine 3D — Ideas, observations, and research backlog

Last updated: 2026-10-14
Status: DISCUSSION / NOT AUTHORIZED FOR IMPLEMENTATION

This is a durable record of the user's observations and future feature ideas for Slot-21. It is **not** an instruction to change the code, initiate tests, rebuild, or interrupt the currently approved Codex task. Before implementing any item, review the current PROJECT_STATUS.md and obtain explicit approval.

## Confirmed or user-reported field observations

- On version 0.2.0, the user obtained a good, visibly gray model with sharp edges and recognizable surface details; some reflection from the reference boards remained.
- The user disabled automatic exposure and found that an approximately -7 manual exposure reduced laser blooming and unwanted detections. The meaning and valid range of -7 are camera/driver-specific, not a universal preset.
- **Correction to earlier notes:** the room lights were **OFF** when the user fine-tuned the laser for the successful test. Do not describe this as lights-on fine-tuning.
- Version 0.3.0 was tested with approximately the same exposure and dark-room laser tuning in two white-balance configurations (one at the low/off end, one at the high/on end). Geometry remained present, with fewer stray points, but the displayed point cloud looked black. The three-set analysis documented in docs/FIELD_TEST_2026-10-13.md found all-black **stored RGB** in the two 0.3.0 exports. Therefore do not assume it is merely a viewer brightness issue.
- The user also observed that when the object is in view and the 15-frame laser-off background is captured with room lights ON, a subsequent scan may contain object-surface color. Treat the exact sequence/settings as user observations; obtain comparable diagnostics before making causal claims.
- Do not equate an attractive-looking point cloud with known dimensional accuracy; evaluate against known-size objects separately.

## Existing behavior checked in Slot-21 source

- The detector finds laser points throughout the camera image.
- reconstruction.py explicitly separates object-ROI laser points from laser points on the **calibrated left and right reference-wall polygons outside the object box**. It uses both wall segments to fit the handheld laser plane, then triangulates and retains appropriate object-ROI points. **This requested use of the external stripe is already implemented**; avoid implementing a duplicate.
- Exterior laser detections that are not on known calibrated wall/reference geometry are not automatically reliable plane references. Adding such measurements requires verified surface geometry or other constraints, not simply including every outside-ROI pixel.
- The reconstructor has selected the laser-off background image as the RGB source when available; this couples detection-background lighting to surface color and can yield extremely dark/black colors during lights-off scanning.
- Source inspection on 2026-10-13 showed these defaults/limits: 0.75 mm voxel downsampling; ~80 ms capture interval; 2,000,000 raw-point cap; around 10,000 points shown in the live preview. These values need rechecking against the exact version before implementation. Preview density is **not** identical to scan sampling density or measured accuracy.

## Proposed work — ideas only, in suggested order

### A. Separate laser-detection background and color capture (highest relevance)

Current PROJECT_STATUS.md already proposes this correction following the 0.3.0 field comparison; avoid duplicating ongoing work.

- Keep a laser-OFF background reference captured under lighting/exposure conditions matching the **actual laser scan**, preferably matching the successful lights-off workflow.
- Independently capture a properly lit color/texture reference with the object present, laser OFF, and the same fixed camera/object geometry.
- Color capture must not silently overwrite the dark scan's laser-detection background.
- Consider an explicit neutral/visible color fallback when the chosen color reference has unusably dark RGB; preserve the real measured colors separately.
- Changing exposure/white balance can affect image appearance and invalidate a detection background; focus, zoom, image size, or camera pose changes may also invalidate geometric calibration or photo/3D registration. Document and enforce the distinctions.
- Verify with controlled before/after comparisons and record camera settings and light conditions accurately.

### B. More detailed point clouds: separate fidelity from display

**Implemented safe subset in 0.4.0:** Standard 0.75 mm and Fine 0.50 mm voxel
reduction, an immutable per-scan settings snapshot, 10k/50k display-only preview
choices, and visible displayed/total counts. The 0.25 mm experiment, camera
resolution research, raw-profile reprocessing, and accuracy claims remain
deferred pending physical measurement.

- Make **preview point-density** adjustable; the 10k-point screen cap can hide detail that exists in saved geometry. Preserve safe rendering performance with a maximum or adaptive decimation.
- Evaluate optional voxel sizes (e.g. 0.75, 0.5, 0.25 mm), while quantifying changes to noise, size, RAM, processing time, and dimensional error. Smaller voxels preserve more measurements but cannot recover precision the camera/triangulation did not capture.
- Evaluate camera native-resolution choices and calibrated resolution matching; do not claim digital interpolation produces new geometric information.
- Evaluate the capture interval/frame throughput and smoother, slower handheld laser sweeps; changing sampling must not weaken wall-plane quality gating.
- Consider preserving each valid unfiltered laser profile (bounded/raw scan session) to allow later reprocessing at different voxel sizes, without having to rescan; note storage and privacy impact.
- Track three separate metrics: acquired raw measurements, retained/exported points, and currently displayed preview points.

### C. Photo-projected texture / “skin-wrap”

- User wants to photograph the object with lights ON and project its color onto the scanned 3D surface, even if the laser is scanned with lights OFF.
- Feasible for camera-visible surfaces if camera intrinsics, camera pose, object pose, and geometry alignment remain valid. A single photo cannot texture occluded/back surfaces accurately.
- Possible staged outputs: recolor existing points, per-vertex color, then UV-textured mesh (OBJ + MTL + PNG or equivalent compatible format).
- Keep a texture/color photo distinct from the laser-off detection background. If camera exposure changes for the color photo, verify geometry parameters remain stable; prevent autofocus/zoom/reframing changes.
- Consider multiple registered texture photos in a later phase, not as part of the initial feature.

### D. Reference-line usage outside the object selection box

- User asked whether all visible laser-line portions outside the object box can be used to improve triangulation without adding walls to the point cloud.
- **Already done for the two calibrated reference walls**, as checked in reconstruction.py. No new feature is required for that capability.
- Future research only: determine whether extra known reference surfaces, broader wall polygons, or additional reference observations can improve plane stability without introducing reflected lines, unknown surfaces, or false geometry. Never allow outside-ROI wall points into the final object cloud.

## Development and token-efficiency guardrails

- Finish the current approved task first. Treat every item above as a proposal until specifically selected by the user.
- Resume using PROJECT_STATUS.md plus the precise current task; read this backlog only when planning future improvements. Do not reread the entire repository or treat ideas as mandatory work.
- Scope new work narrowly, compare relevant files, retain diagnostics, and test the changed behavior. Preserve camera/geometry safety gates and previously verified baselines.
- Record decisions, implementation status, and exact next action in PROJECT_STATUS.md after an approved milestone. Avoid claiming that planned changes are already built or hardware-verified.

### E. Per-test diagnostic and artifact bundles / repeated independent runs

**Implemented in the 0.4.0 candidate:** the persistent test-run toolbar,
isolated bounded run JSONL, distinct session/run/scan IDs, safe unsaved-run
confirmation, and a sealed complete ZIP with explicit raw/final models,
sidecars, project/calibration/settings, manifest hashes, validation, and
optional images. Physical hardware verification remains pending.

**User request, 2026-10-13:** The user wants one easy-to-upload diagnostic ZIP per complete test run that bundles *all relevant 3D artifacts together* (PLY point cloud, OBJ and STL meshes, their matching JSON sidecars, scan/project data, settings, diagnostics, and optional images). The user wants to complete and export one run, then start a completely new run and export a separate, independent ZIP, without having to close/reopen the application or manually assemble files.

**Current verified 0.3.0 behavior (source checked 2026-10-13):**
- The app already exports a diagnostic support ZIP containing a manifest, a cumulative application-session JSONL log, settings/scan metadata, and optional user-approved current camera/background images.
- Saved PLY, OBJ, STL files, their JSON sidecars, and point clouds are not automatically included. Source limits for the current small *support* bundle are eight optional attachments, 16 MiB each, 32 MiB total attachments, and 42 MiB total ZIP; blindly routing complete scan sets through that mechanism would omit files.
- An application launch has a session UUID; scanning has a separate operation UUID. Re-exporting a support ZIP within the same application session can duplicate much earlier-session diagnostic history. A per-test **run** boundary is distinct from session and scan/pause/resume boundaries.

**Desired future design — one test run, one complete evidence package:**

1. Provide explicit **Start New Test Run**, **Finish Run**, and **Export Complete Run ZIP** actions (or equivalent wizard) with a clearly displayed run number/unique ID. The user can scan, pause/resume, review, export, and save all files for that one run.
2. On finishing/exporting a run, create a single self-contained ZIP with run-scoped diagnostics JSONL, manifest and machine-readable summary; laser settings, captured/read-back camera controls, lens/corner calibration metadata, ROI, background diagnostics; all actual outputs made in that run (PLY, OBJ, STL, JSON sidecars, optional project file and original/filtered scan); and optional user-approved photographs/backgrounds or other evidence. Put artifacts in named folders and ensure each sidecar clearly matches its source scan. Mark absent/unavailable outputs honestly; do not silently invent or overwrite missing exports.
3. Assign distinct **application_session_id**, **test_run_id**, and **scan_operation_id**. Start/pause/resume of the *same scan* stays in the same run; "Start New Test Run" starts fresh run-specific diagnostics/scan data while retaining reusable unchanged camera calibration if permitted. New run should not inherit old point clouds or old log entries by accident.
4. Exporting a ZIP should snapshot and seal the completed run; exporting it twice should not combine unrelated runs. Starting a new run should not alter or discard the previous run's files. Preserve crash recovery and incomplete runs where feasible. A clear "saved/not saved" status and safe confirmation before discarding work is necessary.
5. Keep both a compact privacy-minimized **Support Diagnostics ZIP** and an explicitly opted-in **Complete Test Run ZIP**, or a clear option for full scans/photos. Full exports can be much larger and need appropriate size checks/streaming, integrity hashes and/or split-package handling—not removal of existing bounded-log and privacy protections.
6. Include a manifest listing file paths, byte sizes, SHA-256 checksums, relationships among PLY/OBJ/STL/JSON, application/build version, run start/end, calibration/lighting/camera setting changes, raw/acquired/filtered/display counts, diagnostics status, and any intentionally omitted files. Preserve each original file unchanged; copy into archive, do not relocate it.
7. Allow back-to-back Run 1 / Run 2 / Run 3 test comparisons (e.g. different exposure or white balance) and keep them easily distinguishable by filename, date/time, and run ID. Consider a compact per-run summary/comparison view later.

**Discussion priority:** This is an especially useful workflow idea because the user routinely conducts multiple controlled scanner tests and currently must upload diagnostics plus numerous separate exports/JSON files. However, do **not** start it ahead of the user's current approved Codex task.

### F. Immediate visual photo overlay on the reconstructed object (refinement of item C)

The user's near-term goal is **seeing** the reconstructed object in the app with its real photographed appearance, as if the photo were wrapped over the point cloud/mesh. This is not necessarily a request for fully production-ready UV unwrapping or exports right away.

Suggested simple first-stage workflow:

1. With object/camera/fixture stationary, finish geometric laser capture under whatever lighting yields reliable triangulation.
2. Turn the laser OFF, turn room lighting ON, and explicitly take a **Color/Texture Photo**; keep it separate from the laser-off background used for subtraction, and track changes to camera appearance settings. Avoid focus, zoom, resolution, lens, camera position, or object position changes that would break alignment.
3. Using the saved camera calibration and object geometry, back-project each visible point/mesh surface into the color photo, sample RGB, and show an immediate toggle between (a) neutral-shaded 3D geometry and (b) photo-colored 3D view. The original photo includes background, but the software should **not** map background onto the model: use visible geometry, visibility/depth checks and, where needed, an object mask to avoid bleeding.
4. Initially allow coloring point-cloud points and displaying a photo-projected mesh. Later consider persistent mesh UV/texture export (OBJ+MTL+PNG or GLB/glTF); STL itself cannot store colors/textures.
5. A single camera photo only covers visible front-facing surfaces and can stretch/bleed at silhouettes, holes, and hidden regions; do not invent rear-surface colors. Use neutral/untextured rendering for unobserved parts.
6. This display feature is conceptually separate from increasing the actual point-cloud geometric density (item B) and should not be sold as higher-resolution **geometry**.

**Implementation remains unapproved.** Document as a future visual feature and avoid expanding an already-running Codex task.

### G. Automatic background/corner recognition and moving-camera scans

**User proposal, 2026-10-13 — FUTURE ONLY, not authorized for implementation.** The user would like to replace manually clicking six reference-corner points with automatic identification of the reference background. In a later stage, they want to move the camera slightly around a stationary object while the software still knows where the fixed reference background and object are, enabling additional viewing angles and eventually fusion of multiple overlapping object scans into the same coordinate system.

**Related existing plan:** PROJECT_STATUS.md and docs/FIELD_TEST_2026-10-13.md already defer optional ArUco-assisted corner calibration and multi-view alignment. This backlog item extends the idea into continuous, independently measured camera tracking; do not re-implement existing or currently active work.

#### Phase 1 — Automatically locate the fixed V-corner, leaving camera fixed

- Create a calibrated fiducial board made of **multiple uniquely identified ArUco or AprilTag markers** at accurately measured, fixed locations around the left and right reference wings, near their perimeter, leaving generous uninterrupted matte-white areas for the red laser stripe on *both* walls. Marker ink across the witness line would interfere with laser detection.
- From a checkerboard-calibrated camera and known marker geometry, detect marker corners and solve the fixed reference fixture's 6-DoF camera-relative pose (e.g. multi-marker PnP / robust joint pose refinement). This replaces manual six-point picking, not the separate lens-intrinsic calibration. An ArUco board in OpenCV can represent known markers in a 2D **or 3D** layout.
- Check tag identities, physical dimensions, corner reprojection error, known wall widths/angle and scale, spatial distribution and minimum visibility; reject ambiguous/far-too-few/partly occluded/wrongly measured detections. Prefer markers distributed across **both walls**; one isolated marker is much less robust. Keep manual six-point method as a fallback.
- A markerless alternative could detect the seam, wall edges, and right-angle planes in bright, feature-rich scenes, but a plain white V alone often supplies ambiguous edges. Use markers as the primary practical solution rather than claiming markerless pose accuracy prematurely.
- Test actual marker detection against the user's laser/lighting/exposure workflow. Room-lights-OFF and low-exposure frames may make printed black/white tags invisible; consider a separate lit pose-acquisition frame or controlled illumination that doesn't corrupt stripe detection. Do not assume IR works on all USB cameras.

#### Phase 2 — Reacquire pose when the camera is moved, initially between scans

- Treat the background/fixture and object as **stationary in a shared world coordinate system**; assign every marker/fixture feature a known 3D world position.
- For each new camera position, detect sufficient known markers, solve camera pose in fixture/world coordinates with the original camera intrinsics, and reproject the reference-wall polygons, object ROI, and any depth/occlusion masks into the new camera view. **A fixed 2D green ROI cannot be reused unchanged after camera motion**.
- Recompute the laser plane per accepted frame using wall-stripe intersections at the new pose; intersect object-stripe camera rays with that plane and transform resulting points into the fixture/world coordinate system. Stationary object points from different camera views can then share a coordinate system; estimate residual errors and verify overlap before fusion.
- Important limitation: simply tracking the tags locates the **camera**, not the freely hand-swept laser plane. Both reference wall laser segments (or a separately calibrated alternative to determine laser plane) are still necessary for trustworthy triangulation. Some side angles may obstruct one/both reference wings, requiring a different fixture/laser strategy rather than relaxing validation.
- Suggested initial UX: **Finish side → reposition camera slightly → reacquire markers/verify geometry → scan next side → align and preview overlap**. This staged mode is much safer to validate than freehand simultaneous camera-and-laser movement.

#### Phase 3 — Continuous moving-camera tracking, only after Phase 2 validates

- Solve and update camera pose for every frame or a reliably timestamped tracking sequence, and align profiles into fixture/world coordinates, with detection confidence, landmark residuals, drift/pose jumps, missing tags, and motion blur recorded in diagnostics.
- When markers are temporarily blocked, optionally investigate visual feature tracking/SLAM plus periodic fiducial relocalization, while refusing low-confidence geometry instead of pretending the camera is still localized.
- Static laser-off image subtraction will no longer match a moving camera: design pose-aware scene/reference subtraction or updated matched-pose backgrounds and re-validate the dark-scanning workflow. Also handle any light changes for fiducial detection independently of surface-color acquisition.
- Keep the object stationary until a separate turntable/object-motion model is implemented; do not conflate moving **camera** with moving **object**. Small camera shifts are a sensible first target. Multi-side coverage requires overlap and visibility and can still be constrained by the V-corner, shadows, marker occlusion, and both-wall reference visibility.
- The resulting registered multiple camera viewpoints could later be used for higher-coverage photo projection / texture capture as well as geometry, but avoid inventing hidden surfaces.

#### Explicit implementation boundaries

- Neither automatic corner recognition nor moving-camera 3D alignment is currently verified; the present scanner assumes a stationary camera during scanning.
- Do not claim that placing tags makes moving-camera geometry automatically correct. Document world-coordinate transforms, reprojection/scale errors, stripe support, visibility, timestamp consistency, and quantitative known-object validation.
- Keep existing safety/rejection thresholds, manual calibration fallback, privacy rules, diagnostic recovery, and token-use discipline. Implement only after the user expressly selects this future phase.

### H. Random 3 mm Creality tracking dots on the 90-degree reference fixture

**User idea, 2026-10-13; FUTURE ONLY / EXPERIMENTAL.** Put many Creality 3 mm reflective 3D-scanner sticker dots in irregular positions over the two stationary reference walls. Acquire one well-lit reference image, learn their pattern and known-wall coordinates, then use their detections to recognize/reacquire the fixture when moving the camera. No code requested now.

**Why it may work:**
- Creality sells reflective black-ring/silver-center dots for other 3D scanning systems. The common "3 mm" dot has approximately a 3 mm reflective inner target and 6 mm outer ring (verify purchased size). Random/irregular placement provides a distinctive local constellation, unlike an evenly spaced grid.
- With a calibrated camera, known world geometry of the two fixed panels, and dot centers mapped to the planes (e.g. after measuring panel coordinates or solving world coordinates from a validated reference pose), 2D image observations can support camera-pose estimation using correspondences + PnP/RANSAC.
- A single image of randomly placed, individually identical dots **does not by itself supply metric 3D coordinates or reliable globally unique IDs**. Size alone and a snapshot are not a substitute for measuring/world registration. Resolve dot associations carefully, preferably anchoring the pattern with a small number of uniquely coded ArUco/AprilTags, known panel borders/corners, or a surveyed board layout.
- Dot detection at 1080p depends on working distance, apparent target diameter in pixels, sharp focus, illumination and motion blur. Do a small pilot first, with before/after stills from several angles and actual pixel-level detection statistics.
- Silver reflective points may saturate in dedicated lighting, disappear under the user's lights-OFF/low-exposure scanning mode, or create false red laser highlights. Keep laser witness zones matte and unobstructed; consider a brief dedicated *lit* pose-tracking capture separate from laser frames, or masks preventing marker detections from contaminating stripe fitting.
- If camera moves, the original static background-subtraction frame and 2D object ROI cannot remain valid: pose-reproject the known fixture and recapture/match laser-off backgrounds; continue to require reliable left/right wall stripe support for the freehand laser plane.
- This is a complement/alternative to the ArUco/AprilTag plan in Section G, **not** an implemented feature or a claimed improvement in 3D accuracy.

References for future research: https://store.creality.com/products/3mm-scanner-reflective-markers-for-otter-raptor ; https://cdn.creality.com/ow/official/9f08b8fd-e5da-485b-97ee-5b1a31db6416.pdf

### I. Budget USB camera upgrade and future multiple-camera option

**User request, 2026-10-13; RESEARCH / NO PURCHASE OR CODE AUTHORIZED.** Current webcam is inexpensive ONN/Walmart branded, with limited controls. User wants a reasonably priced camera with better manual exposure/focus/white-balance control and is interested in two or more cameras from different angles.

**Candidates investigated (prices are time-sensitive; verify availability, exact hardware revision and driver support before purchase):**
- Logitech C920/C920s USB webcam, native 1920x1080 @ 30 fps. Practical reliable general-use first upgrade; 78° diagonal FoV; autofocus that should be locked to manual setting for calibrated scans. Typical new pricing around $60–70 (used/secondhand may be less); vendor software and Windows DirectShow manual controls vary. Manufacturer: https://www.logitech.com/en-us/shop/p/c920s-pro-hd-webcam
- Arducam B0454/B0454C 5MP OV5648 USB UVC module, 2592x1944 @ 15 fps MJPEG (1080p @ 30 fps), M12 manual-focus lens, rolling shutter. Often $55–70 through resellers. Offers more pixels for small detail, but wide 110° diagonal stock lens may waste pixels/distort edges, and the official UVC-controls list does **not** guarantee exposure control; verify critical exposure lock before buying. Manufacturer: https://www.arducam.com/blog/product/5mp-ov5648-usb-camera-module-with-wide-angle-m12-lens-and-single-microphone-for-windows-linux-android-and-mac-os/ ; https://docs.arducam.com/UVC-Camera/USB2-UVC-Camera-Kit/Specs-and-Selection-Guide/
- ELP/AR0234 color 2MP global-shutter 1920x1200 UVC machine-vision camera, up to 90 fps for some variants, optional manual/M12 lens, advertised exposure/white-balance adjustment. Found comparable modules around $130–150 (verify true sensor/shutter, specific lens and trustworthy vendor). Preferred as a later motion/precision-oriented experiment; global shutter is useful for laser/camera movement but 2MP alone does not increase pixel density over a 5MP camera. Manufacturer example: https://www.elpcctv.com/elp-2mp-global-shutter-1200p-1080p-90fps-usb-camera-module-with-m12-21mm-lens-p-543.html
- Logitech Brio 100 exists around $38–40 but is marketed as an automatic-light-correction meeting webcam. Its fixed/simple optics and limited controls make it a less compelling upgrade than C920 when manual tuning is paramount.

**Selection tests:** In the actual Windows Scanner app, log/verify supported FPS/resolution, real exposure and manual/auto switching, gain, white balance, ability to keep focus fixed, raw/decoded image quality, sharpness across both calibrated V walls, close-up object focus, red stripe bloom at dark-scan exposure, and ability to detect 3 mm markers under proposed tracking light. Avoid assuming stated megapixels, auto-enhancement or digital zoom improve measured 3D accuracy. Recalibrate intrinsic/extrinsic parameters for each new camera, focus, lens, resolution or zoom configuration.

**Multi-camera staged approach:**
1. Initially add a *second fixed webcam* as a separate independently calibrated view, preferably with one reliable scan camera and another marker/color/reference monitoring view. Test each alone first.
2. For actual fusion, each camera needs its own intrinsics/distortion and pose relative to the shared calibrated V; pair corresponding time-stamped observations, handle USB bandwidth/latency and unsynchronized shutters, and track which camera generated each ray. Compute laser plane reliably, maintain visibility of known reference stripes, and transform each valid object profile into the same world frame. A second camera alone does not automatically make multi-view triangulation, tracking, hidden-surface texture, or scan registration correct.
3. Only later consider multiple simultaneously scanning cameras / moving camera tracking (Section G), optionally using global-shutter cameras and hardware synchronization where real measurements show a need. Preserve the original single-camera path and all rejection/readiness guards.

Keep this as a scoped research/roadmap item. Do not ask Codex to build multi-camera support until the user approves.

### J. Detect real camera resolutions and Windows backend capabilities

**User request, 2026-10-13 — FUTURE FEATURE ONLY; no implementation authorized.** User reports an ONN/Walmart USB webcam (label stock number read as "10028731", possibly "100028731" but **exact model remains unconfirmed**), with existing scanner choices 640x480, 1280x720, 1920x1080 and requested 30 FPS. A candidate Walmart ONN 1440p product was mentioned, but **do not assume this exact physical webcam really supports 2560x1440** without obtaining a valid hardware/driver mode listing or successful capture. It might be a different model or stock number.

**Current code checked 2026-10-13:**
- \`src/laserline3d/ui/pages.py\` hardcodes only 640x480, 1280x720, and 1920x1080 in the resolution combo; FPS is a requested 5–60 input, not a list of independently verified supported per-resolution modes.
- \`src/laserline3d/camera.py\` maps "DirectShow (recommended)" to OpenCV \`CAP_DSHOW\`, "Media Foundation" to \`CAP_MSMF\`, and "Automatic" to \`CAP_ANY\`. It requests width, height, and FPS then reads back reported values. Camera driver dialog access (OpenCV \`CAP_PROP_SETTINGS\`) depends on driver/backend, generally best tried with DirectShow.
- **No existing 1440p menu choice**; changing the selected resolution will require camera/lens recalibration and revalidation of the corner pose, ROI and laser/background as appropriate.

**Future scoped improvement:**
1. Add a **Detect supported camera modes / Refresh capabilities** action that reads the actual available width, height, FPS and pixel format/FourCC combinations exposed by each Windows device/backend (use suitable Windows DirectShow/Media Foundation capability enumeration when OpenCV alone cannot reliably list the modes); preserve the hardcoded 1080p choices as an offline fallback.
2. Show verified choices such as **2560x1440 at 30 FPS only if offered by that camera**, plus any other real formats. Allow a clearly marked *advanced custom/requested mode* for experimentation, but never present an unsupported mode as proven.
3. Display both **requested** and **actual reported/captured** resolution, format and FPS. Measure effective delivered frame FPS and scanner **processed/accepted** FPS separately so the user can see if the current ~80 ms processing submission interval or dropped frames limit the actual point-cloud density; a "requested 60" field alone does not make the device 60 FPS.
4. On mismatch, warn and offer a supported fallback. Handle MJPEG vs uncompressed formats and USB bandwidth/performance without forcing unsafe camera properties or making preview freeze.
5. Preserve selectable **DirectShow / Media Foundation / Automatic**. Use DirectShow as the practical first test when access to native camera settings and manual exposure is needed; Media Foundation as a fallback if DSHOW fails or has inferior format support, then Automatic if necessary. Verify behavior using the particular ONN webcam; automatic selection does not guarantee the desired controls.
6. Include camera mode and backend in saved calibration identity, run diagnostics, and complete-run ZIP. Warn/invalidate when changes affect camera calibration or the laser-off background; do not reuse an old camera calibration at a new resolution just because aspect ratio matches.
7. Test on the actual connected ONN webcam before recommending a new camera. Higher resolution may provide more laser pixels but is not automatically a gain in depth accuracy; FPS and image quality may drop at a higher mode.

**Priority:** Useful low-cost improvement after the current approved task, and a prerequisite for objective comparison of the present ONN webcam versus possible camera upgrades. This backlog note is *not* a Codex instruction to make changes now.

### K. Higher-precision red stripe sampling and point density

**User observation / idea — 2026-10-14. Future research only; do not modify code until approved.**

During scanning, the user zoomed into the live video and saw little **green dots along the red laser stripe**, and asked if the "laser-line resolution" could be improved independently of the webcam. This is distinct from increasing the photo/camera resolution (Section J), raw profile capture rate (Section B), 3D voxel density, or preview drawing density.

**Existing implementation checked in source on 2026-10-14:**
- On Tune and Scan video overlays, laser samples belonging to the **object ROI** are drawn green, while reference-wall samples are cyan. They are detected stripe positions, not guarantees of final accepted 3D points.
- \`laser_detection.py\` uses a red-score mask and per-column ridge selection for a horizontally oriented stripe; then calculates a brightness-weighted **subpixel center** within the configurable stripe half-width (currently default 2 px), followed by a continuity filter. Hence a visible string of green dots corresponds to selected stripe locations, typically up to one location per occupied image column, not individual laser "projected pixels."
- \`reconstruction.py\` triangulates only valid object-region samples after plane fit, angle/depth, and geometry gates. \`ScanAccumulator.cloud()\` voxel-downsamples the accepted profiles, with default 0.75 mm voxel size. Preview output may also decimate significantly.

**Research and tests to prioritize if approved:**
1. Determine whether optical stripe width is a limiting factor, using actual screenshots of line full-width, saturation, center stability, and missed columns at the user's working distance. Evaluate an **adjustable-focus low-power line laser**, proper positioning, matte fixture, manual exposure/gain and existing dark-room technique; seek a narrow *but still continuous and bright enough* stripe. Do not recommend increased power or unsafe direct/reflected exposure.
2. Measure subpixel localization repeatability at known, fixed geometry, including laser speckle and surface reflectance. Compare current brightness-weighted ridge-center estimator with intensity-profile Gaussian/parabolic fit or other robust subpixel methods, only when improvements are shown on real representative frames and noise does not increase.
3. Characterize sampling **along** the line (native horizontal image columns / actual object ROI width) versus sampling **across** the sweep (accepted frame rate, drop rate, hand motion) versus voxel merging. Do not confuse drawing more dots/interpolation with acquiring new independent geometric information.
4. Track raw detected line samples, triangulated valid points, accepted profiles, voxelized/exported points, and displayed preview counts independently. Expose diagnostic gaps between stages and allow safe adjustable sampling/voxel density if tests warrant.
5. Improve precision without weakening two-wall reference triangulation, low-angle and residual rejection, or reference geometry constraints. New lens/focus/zoom/resolution changes require calibration revalidation.

This is an exploratory detail/accuracy proposal, not an active task or a reason to restart Codex work.

### L. Camera-assisted manual laser focus and magnified preview

**User proposal, 2026-10-14 — future concept, no code implementation approved.** The adjustable-focus red line laser appears focused to the user's eye, but the user wants a dedicated **Laser Focus Assistant** that watches the stripe on the reference boards while they turn the laser's physical focus ring and tells them when the best focus is reached. Their ONN webcam lacks an optical zoom; they would also like to zoom into the stripe and/or get physically closer to the object without losing calibration. Evaluate as a future separate **optical focus/tuning** stage, not a replacement for checkerboard lens calibration, V-corner calibration, or the mandatory laser-off background.

**Current scanner facts checked from source on 2026-10-14:**
- \`laser_detection.py\` estimates subpixel stripe centers with intensity-weighted neighboring pixels but does not provide a dedicated measured stripe-width (e.g. FWHM) focus score or tell the user when to stop turning a focus ring.
- \`ui/widgets.py\` VideoCanvas has existing scroll/button *view-only* zoom and pan, up to 8×, based on display scaling. It magnifies existing pixels and dots for inspection but **does not add new sensor detail**, modify camera optics, or change triangulation coordinates. Distinguish this from camera/driver digital zoom or changing the actual capture resolution/crop, which may invalidate calibration.
- Laser tuning currently uses background subtraction, red mask thresholds, laser-center samples, saturation fraction and reference-plane readiness; any new score should reuse available evidence but measure laser stripe *width* directly, without assuming green-dot count alone means good focus.

**Practical proposed Laser Focus Assistant flow:**
1. Fix the **camera lens focus, physical camera position, capture resolution, exposure, gain and white balance** first; ensure image is actually sharp. Recalibrate camera intrinsics and corner pose if necessary, then leave camera unchanged while tuning laser optics. Otherwise camera blur or exposure changes can masquerade as laser focus changes.
2. Aim the laser at an appropriate matte, uniform part of the reference fixture (or a temporary matte target) at the **intended object depth**, avoiding reflective stickers and keeping eye safety. Focus should be assessed over several regions/distances when the laser spans the left wall, object and right wall, since one focal setting may not be best over the full 3D volume.
3. Capture multiple stable frames with the laser ON and a matched laser-OFF reference; form intensity profiles **perpendicular** to the stripe in the original camera pixels (not an enlarged displayed view). Estimate median width at half maximum (FWHM or robust equivalent), line continuity, percentage clipped/saturated pixels, signal above background, center-position jitter, and spatial variation.
4. Display a high-magnification **non-interpolated 1:1 or pixel-grid inset**, live width and quality metrics, history graph and best-so-far marker; ask the user to turn the **physical laser focus ring slowly**. When the width stops improving or grows again, prompt "Best observed focus reached—stop or turn back slightly." Optional beep and explicit confidence indicator. Only indicate "optimal within this observed adjustment sweep," never absolute optical best.
5. Do **not** select merely the narrowest reported bright/red candidate if signal becomes too weak, disconnected, specular, saturated, or unstable. Require enough valid stripe coverage and measured subpixel center stability, compare multiple regions, and use conservative rejection/warnings. Study repeatability before changing thresholds.
6. Save a per-camera/laser-distance focus report and observed recommended settings as **guidance only**; physical knob setting has no readable numeric encoder. The focus assistant doesn't remove the need to verify triangulation and keep laser plane visible on both calibrated walls during actual scanning.
7. If user wants a larger image of the object, keep the distinction:
   - **UI preview zoom**: already implemented, safe for calibrated geometry, shows existing pixels larger; useful for manual focus and inspection but doesn't create detail.
   - **Move camera physically closer and/or use an actual narrower optical lens**: gives object more sensor pixels, potentially raising spatial sample density, but both reference wall laser segments and requisite fixture landmarks still must remain visible. Moving the camera or changing physical/driver focus/zoom/lens requires appropriate new calibration; inspect field-of-view and near-focus working distance first.
   - **Camera-driver digital zoom/crop**: may resample or crop and change effective intrinsics; do not assume this raises true resolution or allows reuse of calibration.
   - Later, a second calibrated camera could view the reference fixture while a closer/narrower-FOV camera sees object detail, but this requires multi-camera triangulation and reliable extrinsic registration (Section I).
8. Treat *physical* laser focusing as a quality-control step; changing only laser focus (not camera settings/pose) normally does **not** invalidate the geometric camera lens calibration, but rerun laser stripe tuning and verify the left/right reference-plane fit after adjustment.

**Status:** Research-backed possible approach (stripe width measurement is an established machine-vision technique), **not developed or user-verified in Slot-21**. Preserve pending task boundaries, existing safety and recovery standards, and do not start Codex work on this idea until the user approves.

Reference: https://pmc.ncbi.nlm.nih.gov/articles/PMC7249136/ (laser stripe-width estimation and exposure interaction); https://pmc.ncbi.nlm.nih.gov/articles/PMC4436288/ (effect of saturation on stripe-center estimation).

### M. Preferred path: marker-based closer-camera setup vs two cameras

**User's latest explicit priority, 2026-10-14. Discussion/memory only; do not implement until approved.** The user likes the future **two-camera wide reference + close-up detail idea**, but prefers first to investigate **automatic board pose recognition using ArUco/AprilTag markers or randomly arranged Creality 3 mm reflective dots**, with the goal of moving a *single camera closer* to see finer object detail **without requiring all six existing V-corner landmarks to stay in the image**. The current single ONN webcam has no optical zoom; existing UI zoom enlarges already captured pixels and does not add 3D measurement detail. The physically adjustable-focus red line laser is already near the sharpest focus by eye, and the proposed Laser Focus Assistant in Section L remains desirable.

**What marker-based pose can and cannot guarantee:**
- Use a checkerboard-calibrated camera (known lens intrinsics/distortion), **known marker physical dimensions**, and **known marker locations/orientations relative to the measured two-wing 3D fixture**. Sufficient clearly visible uniquely identified ArUco/AprilTag corners can estimate the **camera's 6-DoF pose relative to the fixture** and thus reproject fixture edges, polygons and ROI after moving the camera. An initially surveyed/validated marker layout and accurate printing/flat mounting matter.
- Markers are **not omniscient at any distance/angle**: extreme tilt, glare, motion blur, defocus, distance too great for adequate pixel size, cropping, low light, occlusion, and poor distribution can prevent identification or make pose estimates inaccurate. Several spread-out markers on **both noncoplanar reference walls** are preferred; retain confidence/reprojection checks and the manual six-point method as a fallback.
- Creality reflective tracking dots have a known target diameter, which helps scale/centering, but unlike coded ArUco tags, individual dots have **no unique ID**. To recover camera pose consistently, accurately map each dot's 3D location in the fixture coordinate system once, then match the observed **irregular constellation** with enough dots across both wings. A hybrid (a few printed coded IDs as anchors + extra 3 mm dots) is promising, but marker-on dark/low-exposure images and laser-reflection interference require tests.
- **CRITICAL GEOMETRIC LIMITATION:** In Slot-21, locating the fixed board does **not** locate the freely handheld laser sheet in each frame. The existing reconstruction fits that plane using the laser stripe visible on **both measured V reference walls**, and triangulates the stripe on the object. If a closer/narrower camera sees only the object or only one reference stripe, its marker-based pose alone **cannot continue the existing valid reconstruction**. Do not weaken reference-segment safety checks or suggest replacing wall stripes with dots.
- As a result, merely replacing six manually clicked points with tags may make setup and modest camera repositioning far easier, **but does not ensure that the camera can move arbitrarily close**. An initial camera repositioning test should measure the usable field of view: enough tags **and** long enough laser-visible segments on both walls at all relevant sweep positions. Additional measured close-in witness surfaces or a separately calibrated laser-plane sensing arrangement would require design and validation.

**A staged, hardware-frugal research and test sequence:**
1. On the existing ONN camera and 90° fixture, test correctly scaled, distinct ArUco/AprilTag markers near perimeter edges of **both panels** without covering the matte white reference-stripe zones. Capture bright marker images; document marker physical dimensions, pose residuals, and how many markers/corners remain visible at near/far camera distances and tilt angles. If desired, compare with a pattern of Creality 3 mm dots and a hybrid. Keep camera fixed during scans until tracking is validated.
2. Test **reacquisition only between scans**: move camera to a new fixed position, detect sufficient markers, solve/refine new world pose, recapture/calibrate appropriate backgrounds and ROI, then test known-dimension object geometry. Avoid interpreting preview zoom as physical zoom. If focusing the camera at new object distance, redo lens calibration as needed.
3. Specifically measure whether the closer camera still captures both required wall laser segments with adequate length/angle and sees the object at every useful stripe position. If not, record that as a **geometry visibility limit**, rather than relaxing acceptance checks. Camera closer can raise useful pixels per object but may invalidate depth accuracy/coverage if witness stripes disappear.
4. If a single close-up camera cannot fulfill both requirements, pursue the alternative **two-camera architecture** (Section I): a fixed wide-view camera sees and measures the two wall witness stripes and estimates the handheld laser plane; a narrower/closer, separately calibrated camera captures the object stripe in more pixels. Use known relative camera extrinsics to transform rays/laser plane, timestamp or synchronize frames tightly enough for the handheld moving laser, handle unequal exposures and USB latency, and validate on known dimensions before fusing. This is a **future nontrivial reconstruction change**, not a plug-and-play second camera; possible roles for the second camera include color/marker tracking as simpler early tests.
5. Keep a separate low-risk **Laser Focus Assistant** (Section L) that measures stripe width/saturation/continuity and tells user when to stop turning the laser's focus ring; its magnified UI preview should preserve original image pixels.
6. Do not recommend a new camera purchase before comparing ONN's actual capabilities/mode enumeration (Section J) and a measured single-camera field-of-view/detection trial. Larger sensors or better lenses are options, not substitutes for calibrated reference visibility.

**Current-state distinction:** Section M summarizes a **preferred research direction**, not an active build. Current 0.3.0 still assumes a fixed camera, fixed V and manual corner landmark selection; neither automatic markers nor dual-camera scanning has been verified. The next approved Codex work remains whichever task is recorded in PROJECT_STATUS.md; do not interrupt it or consume extra Codex usage to implement discussion items.

**Recent conversation coverage map (Sections A–M):**
- Dark detection background vs well-lit independent RGB capture, all-black 0.3.0 point colors and photo overlay/texture mapping: **A, C, F**, plus FIELD_TEST_2026-10-13.
- Increase native resolution and actual FPS, raw/voxel/display point densities, finer laser ridge points and subpixel accuracy, green dots on stripe: **B, J, K**.
- Exterior detected laser line already used on **both known reference walls** for the plane, but not as object cloud points: **D**.
- Complete individual scan-run ZIP packages with scans PLY/OBJ/STL, JSON sidecars, images by consent, and per-run diagnostics, repeated without restarts: **E**.
- Auto board recognition with ArUco/AprilTags, moving camera between scans, later live tracking, random 3 mm Creality dots, potential hybrid: **G, H, M**.
- Cheap Windows USB camera research (ONN 1080p with possible higher unconfirmed resolution, Logitech C920s, Arducam 5MP/8MP, future global shutter), DirectShow/Media Foundation mode detection, multiple cameras: **I, J, M**. Specific retail availability/prices change and do not imply confirmed hardware capability.
- Laser focus assistant; physical vs preview/driver digital zoom and optical camera distance problem: **L, M**.

**Preserve the user's intent:** keep this information in durable Slot-21 repository memory, useful for future planning and Codex resumption, **without making these ideas immediate instructions or sacrificing usage/recovery efficiency**.

### N. Multi-scale ArUco reference markers with measured increments

**User idea, 2026-10-14 — proposal only, do not implement until approved.** On the existing adjustable two-wing V fixture, combine **large uniquely identified ArUco tags near the six traditional reference landmarks** (far-view recognition) with **smaller uniquely identified ArUco tags at surveyed increments** on both wings (near-view recognition). The user specifically wants repeatable, *measured* locations, not arbitrary small-marker scatter. This reinforces the user's preference for automatic markers before a second camera (Section M).

**Physical coordinate layout rather than a fixed proprietary board size:**
- Use a fixture-coordinate origin such as **hinge seam / bottom reference height**. For each left/right wing, record local distance **along that panel from seam** (mm) and **height from origin** (mm); transform into 3D using the measured inside angle. Parameterize current wing width, marker-height span and hinge angle; current software's wing widths are equal.
- The six canonical landmarks remain geometric points: left outer top/bottom, hinge seam top/bottom, right outer top/bottom. Place large tags **adjacent to**, not centered directly over an edge/hinge seam, and record exact physical offsets between marker corners and intended world landmarks; tags do **not** make their own centers equal to the existing landmark positions.
- Start as a **prototype**, not a verified print design: large tags roughly **40–60 mm square** with enough white quiet border for far view and near the six landmark neighborhoods; supplementary tags roughly **20–25 mm square** along perimeter/side strips at **50 mm (approximately 2 inch) measured center-to-center increments**, where they physically fit. Printed ruler/tick markings at e.g. **10 or 25 mm** provide finer scale without needing a separate tag at every tick. The user can choose exact mm/inch increments. Verify tag pixel size and count at current 1080p working distances before finalizing; 3 mm ArUco tags are generally too small for far-view webcam recognition.
- **Every tag has a unique ID** in the selected dictionary, independent of its physical printed size. Each stores its **own measured square side length and four 3D corner coordinates**; include a board map/manifest (ID, size mm, panel, origin/offset, 3D corners, print scale, revision). A custom OpenCV ArUco \`Board\` of 3D marker corners supports noncoplanar, different-size markers; the plain fixed-spacing \`GridBoard\` is not the right assumption for this mixed-size V.
- Detector can use any reliable subset at different apparent scales. Require enough well-distributed in-focus tags from both wings and reprojection checks; do not imply that all six tags or any arbitrary combination of tiny markers always suffices. Camera lens calibration remains separate.
- Leave broad matte-white, unmarked laser witness strips on *both walls* and protect the red line from printed markers/reflections; the software still needs laser-wall measurements to compute the **freehand laser's plane each frame**, even after markers locate the camera. Measure marker visibility under lights-on pose setup vs lights-off red-line scanning.
- Printed tags must be at actual measured size, flat and attached rigidly; adhesive placement or fixture angle changes require an updated surveyed map / pose calibration. Reprojection of the six original landmarks can be visualized from the solved board pose even when the original marks themselves are out of frame.
- Staged validation: first test fixed-camera detection, then record closer camera poses **between separate scans** and compare 3D ground-truth objects. The closer camera must still see sufficient wall laser stripes on both wings, otherwise use the previously recorded **wide reference camera + close object camera** concept, with separate calibrations and time alignment.

Official OpenCV API: https://docs.opencv.org/4.13.0/d4/db2/classcv_1_1aruco_1_1Board.html (user-defined ID and 3D corners for each marker, mixed layout).

**Status:** recorded as an idea only; preserve current Codex task, diagnostics and safe geometry constraints.
