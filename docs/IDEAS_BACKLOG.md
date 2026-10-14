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
