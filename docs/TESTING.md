# Verification and hardware test plan

## Test This Version — Windows candidate 0.5.0

This is the guided user test for the 0.5.0 development candidate. It is not a claim
that the camera/laser hardware is already verified. Use a freshly extracted
release folder; never merge it into an older `_internal` folder. Keep the
fixture, camera, focus/zoom, room lighting, and object stationary unless a step
explicitly says otherwise.

The toolbar starts one isolated test run automatically. Use **Save diagnostics
ZIP…** for a compact mid-run problem report. At the end, use **Finish test &
save complete ZIP…** exactly once as the last action; it packages the run-only
trace and all 3D outputs. Then use **Start new test run** before the next test.
Choose whether the two camera images may be included, and review any ZIP before
sharing it. Do not repeat a failing setup many times without reviewing evidence.

1. **Launch and software self-test — no camera or laser required.** Open
   `LaserLine3D.exe`, press **Run built-in synthetic self-test**, and wait.
   Expected: the app remains open and shows a generated model with accepted
   frames, points, and triangles. Automatic evidence: the deterministic CLI
   release test must also report 24 accepted frames, 4,316 points, 8,334
   triangles, and about 1.45 mm median virtual-plane error.
2. **Test-run boundary — no hardware required.** Confirm the top toolbar says a
   short test-run ID is recording. Press **Start new test run** once before any
   physical setup. Expected: scan/review data reset, while reusable calibration
   and an unchanged background remain available; a run with unsaved scan data
   must warn before it is abandoned.
3. **Camera connect/reconnect — no scan required.** Select the intended backend,
   resolution, requested frame rate and USB video format, then press **Connect**.
   For the Arducam B029201, first test MJPEG at 3264 × 2448 / 15 fps, then
   MJPEG at 1920 × 1080 / 30 fps. Verify moving live video and compare the
   reported actual resolution/rate/FourCC with the request. A substituted mode
   must be shown as a warning and recorded as `camera_mode_negotiated`, never
   silently treated as accepted. Then **Disconnect** and reconnect. Expected:
   no old still frame is treated as live, and any saved laser-off background is
   marked for recapture. If camera identity, resolution, focus, autofocus, or
   zoom changed, lens/corner calibration must be invalidated rather than reused.
4. **Camera controls and profiles — no scan required.** Press **Camera driver settings…**,
   disable automatic focus/exposure/white balance when available, lower
   exposure/gain enough to keep the laser narrow, close the driver window, then
   press **Refresh reported values**. Expected: raw values update; changing a
   relevant control requires a new background, and focus/zoom changes require
   calibration again. A raw zero may mean unsupported. Expected diagnostics:
   exposure, gain, brightness, contrast, saturation, hue, gamma, sharpness,
   backlight, focus, white balance, zoom, FourCC, buffer and any available
   temperature/iris values are timestamped with support caveats. A changing
   sensor-temperature reading alone must not invalidate the background. Next,
   select only **Exposure** and **Gain** in the in-program profile, enter the
   driver's reported raw values, and press **Apply selected controls**. Expected:
   each requested value shows its actual read-back as applied, substituted,
   refused, or unreported; no generic range is assumed. Save the named JSON
   profile, change both form values, load it again, and verify loading restores
   the requested mode/control fields but does not silently apply or reconnect.
   Apply after loading and verify a changed exposure/gain invalidates the
   laser-off background. Separately apply a changed focus/autofocus/zoom value
   only if safe for this test; it must invalidate lens and corner calibration.
   **Camera driver settings…** must remain available as the fallback.
5. **Lens calibration.** Capture at least 12 varied checkerboard views and press
   **Calculate and save calibration**. Expected: accepted-view count increases
   only for detected boards and the result reports reprojection error. Human
   check: views cover the centre, four corners, near/far distances, and tilts.
6. **Corner and object area.** With an empty V, press **Freeze this view for six
   clicks**. Put the pointer near each corner and use the wheel: the same image
   feature must stay under the pointer while zooming. Left-drag, right-drag, and
   middle-drag must pan; a left-drag must not add a point. A short left-click
   adds one point. Exercise Undo once, mark all six, then **Solve corner pose**.
   Place the object, press **Capture object view for green box**, and draw a tight
   box. Expected: pose solves, the green box contains only the object, and clear
   laser witness-wall area remains on both sides. Record the reprojection RMS;
   2.00 px or lower is recommended.
7. **Laser background and tuning.** Keep room lighting at its final steady level,
   turn only the laser off, and press **Capture 15 laser-off frames**. Turn the
   laser on, try **Auto-suggest from laser-on view**, and use **Restore defaults
   (120 / 45 / 55)** if needed. Expected: one thin continuous green/cyan trace,
   very few isolated dots, acceptable left/right reference counts, long wall
   spans, support at or above the displayed recommendation, and no background-
   mismatch warning. Human failure: broad saturated glow, speckle, or detection
   away from the laser. Wait until at least five consecutive previews are Good.
8. **Readiness guard.** First press **Start scan** after five stable Good
   previews. Expected: scanning begins. Pause, return to Tune laser, then make
   the support unstable or let the background differ and try again. Expected:
   a warning lists the reason and defaults to returning to Tune laser. Use
   **Start anyway (diagnostic run)** once only to verify that the override is
   explicit and logged; do not treat override data as accurate.
9. **Density and preview controls.** Before scanning, leave **Point-cloud
   detail** at Standard (0.75 mm). Verify Preview detail changes between 10,000
   and 50,000 displayed points without changing a saved/exported point count.
   Clear the scan, select Fine (0.50 mm), and repeat the same controlled sweep.
   Expected: Fine may retain more measured samples and use more time/memory; it
   must not be described as added camera detail or dimensional accuracy. The
   density selector locks as soon as the scan owns data.
10. **Stationary scan state.** Press **Start scan**, sweep slowly, verify the
   label becomes **Scanning…**, press **Pause**, then **Resume scan** without
   moving the object. Finish with **Finish and review**. Expected: accepted and
   rejected frame totals make sense, the preview is visible in High contrast,
   and the button never misleadingly remains **Start scan** while capturing.
11. **Cleanup/repeated-Finish regression.** Finish, press **Remove isolated
    dots**, build the surface, note the exact point/triangle counts, return to
    Scan, and press **Finish and review** again. Expected: the cleaned point
    count and mesh remain unchanged. Resume and accept one genuinely new frame;
    expected: the old cleanup/mesh is invalidated and must be regenerated.
12. **Clear/restart regression.** Press **Clear scan**, confirm zero frames and
   points, then start another sweep. Expected: no delayed points from the prior
   scan appear, and the preview does not turn black because of dark measured
   surface colors. Switching to **Measured surface colors** may look dark but
   must not change saved/exported RGB values.
13. **Deliberate failure guidance and watchdog.** One at a time, hide a
   reference wing, make the laser angle too shallow, sweep too quickly, and
   briefly create an overexposed stripe. Expected: machine-readable reasons
   distinguish missing left/right wall, ambiguous support, low angle, depth,
   volume, and broad/blurred line. For low angle, translate the line up/down
   while keeping long segments on both walls; do not pivot toward the seam.
   Finally remove the line for 50 processed frames. Expected: scanning pauses
   automatically instead of logging indefinitely.
14. **Manual save and export.** Save `.llscan`, PLY, OBJ, and STL; reopen the project and
    inspect the formats in Blender/FreeCAD/OpenSCAD. Expected: non-empty outputs
    open successfully. Human check: this is an open, camera-visible surface—not
    an invented watertight back.
15. **Diagnostics evidence/privacy/export.** Use several in-app keyboard and
    mouse actions, then press **Save diagnostics ZIP…** once with
    images excluded and, if acceptable, once with images included. Expected:
    each ZIP opens; `manifest.json` and the JSONL log parse; no point cloud is
    included; local user/workspace prefixes are redacted; camera/image metrics
    and separate inside/outside-green-box scan evidence are present; the JSONL
    is no larger than 8 MiB. Key records contain only command categories,
    modifiers and widget context—not typed characters or field contents. Review
    images before sharing. Return to the completed physical scan and make
    **Finish test & save complete ZIP…** the final action. Expected: one ZIP
    contains `manifest.json`, run-only `diagnostics/events.jsonl`, run settings
    and summary, raw/final PLY files, final OBJ/STL, every matching JSON sidecar,
    camera/corner calibration, and `project/scan.llscan`. Manifest sizes and
    SHA-256 values validate; images are absent when declined. The finished UI
    is read-only until **Start new test run** is pressed. A second run ZIP must
    contain only its own test-run UUID and events.

Record each step as `MANUAL_PASS`, `MANUAL_FAIL`, `BLOCKED`, or `UNTESTED`, plus
the camera model/backend/resolution and a short note. Version 0.4.0 becomes a
hardware-verified baseline only after the required physical steps pass; a build,
launch, or synthetic PASS alone is insufficient. The structured session log is
the authoritative automatic evidence for this candidate. See
`DIAGNOSTIC_COVERAGE.md` for the event/result map.

## Automated no-camera verification

Install the project, then run:

```powershell
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe -m laserline3d --self-test --self-test-output test_reports\self_test
```

The self-test creates a deterministic virtual camera, two known reference
walls, a moving laser sheet, and a flat object at a known depth. It exercises
red-stripe detection, reference-plane intersections, robust laser-plane fitting,
object triangulation, point fusion, meshing, binary PLY, and binary STL. Passing
this test verifies software geometry; it does **not** verify a physical camera,
laser, fixture, or real-world accuracy.

## Guided first-hardware test

1. Build and accurately measure the two-wing rig.
2. Fix the camera and complete lens calibration at the intended resolution.
3. Complete corner setup and save both JSON profiles.
4. Place a flat matte card at a measured depth and scan it.
5. Export PLY and compare fitted-plane flatness and dimensions to caliper/ruler
   measurements.
6. Scan a known rectangular block and compare width, height, and visible depth.
7. Repeat the same sweep three times without moving the setup. Compare the three
   clouds for repeatability.
8. Test the explicit failure guidance by hiding each reference wing, overexposing
   the stripe, moving quickly, and changing camera resolution.

Record camera model, USB port/backend, resolution, exposure/focus settings,
fixture measurements, calibration errors, object measurements, exports, and
diagnostic JSONL path. Only then create a hardware-verified baseline.

## Release package test

Build with `build_windows.ps1`. It creates and tests a staging package first,
checks the required OpenCV configuration files, and only then publishes
`dist/LaserLine3D_<version>` and records that folder in
`dist/CURRENT_PACKAGE.txt`. If the app is still running, publication stops
without partially deleting the working package. On a clean Windows 11 x64 PC
with no Python:

1. copy the complete versioned folder named by `dist/CURRENT_PACKAGE.txt`, or
   extract the complete release ZIP into a fresh location (never merge it into
   an older folder);
2. launch `LaserLine3D.exe`;
3. run the synthetic scan from the welcome page;
4. export PLY, OBJ, and STL and open them in Blender/FreeCAD/OpenSCAD;
5. connect the Arducam B029201 and verify its requested/actual modes plus the
   selected camera-control profile read-back through DirectShow (and Media
   Foundation as a compatibility check);
6. close/reopen the program and inspect `%LOCALAPPDATA%` diagnostics.
7. complete a synthetic or small controlled scan, save the complete test ZIP,
   validate every entry, then start a second run and confirm run isolation.

The initial supported package is PyInstaller **onedir**, not onefile. Onedir is
easier to diagnose, starts faster, and avoids antivirus-sensitive temporary
extraction.
