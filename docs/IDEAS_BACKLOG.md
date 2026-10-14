# LaserLine 3D — Ideas, observations, and research backlog

Last updated: 2026-10-13
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

**User request, 2026-10-13:** The user wants one easy-to-upload diagnostic ZIP per complete test run that bundles *all relevant 3D artifacts together* (PLY point cloud, OBJ and STL meshes, their matching JSON sidecars, scan/project data, settings, diagnostics, and optional images). The user wants to complete and export one run, then start a completely new run and export a separate, independent ZIP, without having to close/reopen the application or manually assemble files. The user previously discussed this with Codex; **first verify what Codex may already have implemented** before doing any work. This is a proposal only.

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
