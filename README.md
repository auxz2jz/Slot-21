# LaserLine 3D Scanner

LaserLine 3D is a Windows desktop application that turns a red laser stripe,
a fixed USB camera, and a simple V-shaped reference corner into a 3D point
cloud and surface mesh. It is designed for Logitech UVC cameras but works with
other Windows cameras exposed through Media Foundation or DirectShow.

The application exports:

- coloured PLY point clouds (the lossless primary scan);
- OBJ surface meshes for Blender and FreeCAD;
- STL surface meshes in millimetres for FreeCAD and OpenSCAD.

## Why the reference corner is required

A camera can see the laser stripe, but it cannot determine where a freely held
laser projector is in 3D. LaserLine 3D solves that ambiguity on every video
frame. Keep the stripe visible on the object **and** on the two non-coplanar
white panels of the calibration corner. The two reference segments determine
the laser sheet plane; camera rays through the segment on the object can then
be intersected with that plane.

This means the projector may be swept by hand. The camera and reference corner
must not move after setup calibration.

## Hardware setup

1. A Windows 10/11 PC with Python 3.12 (64 bit).
2. A fixed Logitech/USB camera with autofocus and auto-exposure disabled when
   possible.
3. A low-power red line laser. Wear appropriate eye protection and never aim
   the beam toward eyes, reflective surfaces, or the camera operator.
4. Two flat, matte-white panels joined vertically at 90 degrees to make a
   concave `V`. Recommended inside dimensions are 300 mm per wing by 400 mm
   high.
5. The supplied [US Letter checkerboard](output/pdf/LaserLine3D_Checkerboard_9x6_Inner_25mm_Letter.pdf)
   printed at Actual size / 100% and mounted flat to rigid backing. It has
   10 x 7 printed squares, 9 x 6 inner corners, and 25 mm squares.

The checkerboard and V are separate calibration items. Move and tilt the
checkerboard through the future object volume for lens calibration; do not
leave it flat on the base and do not attach it to the V. The V wings remain
plain matte white. The base may be plain matte white or neutral gray; avoid
red, black, glossy, mirrored, or transparent material.

Place the object centrally in front of the V seam. Frame the scene so the left
wall, object, and right wall are all visible. Sweep a roughly horizontal laser
line from top to bottom. The stripe must reach clear wall area on both sides of
the object in every accepted frame.

## Install and run from source

A software-tested Windows 0.2.0 **candidate** is available at
`dist/LaserLine3D/LaserLine3D.exe`, with the complete release ZIP in
`output/windows/LaserLine3D_Tuning_Diagnostics_Update_0.2.0_2026-10-12.zip`. Keep the
complete `LaserLine3D` folder together; the executable depends on the adjacent
`_internal` files. `run_scanner.bat` uses this packaged copy when it is present
and falls back to the source environment only when no package exists.

If an older package reports `DLL load failed while importing QtCore`, discard
that entire old package folder and use the newly built folder. Do not copy only
the new `.exe` over old `_internal` files.

For the packaged release, double-click `run_scanner.bat`. Source developers can
run `install_windows.bat` first to create the fallback Python environment.

Or from PowerShell:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -e .[test]
.venv\Scripts\python.exe -m laserline3d
```

Run the hardware-independent verification suite with:

```powershell
.venv\Scripts\python.exe -m laserline3d --self-test
.venv\Scripts\python.exe -m pytest
```

## Guided workflow

1. **Camera** – select the Logitech camera, choose a resolution, lock camera
   settings if the driver allows it, and do not change them after calibration.
2. **Camera lens calibration** – use the printed checkerboard in at least 12
   varied positions, distances, and tilts. Run calibration and save it.
3. **Empty-corner setup** – remove the object, turn the laser off, enter the
   measured V dimensions, freeze a clear image, and click the six prompted
   marks. Zoom and pan as needed, then solve the pose.
4. **Object area** – place the object without moving the camera or V. Click
   **Capture object view for green box**, then drag a tight rectangle around
   only the object. Wall stripe outside the box remains reference data.
5. **Laser tuning** – with the object in place, keep the room lighting and camera
   settings exactly as they will be during the scan. Turn only the laser off and
   capture the 15-frame background, then turn it on. Start with **Auto-suggest**
   or **Restore defaults** and tune for one thin continuous detected trace.
6. **Scan** – start capture and sweep slowly without moving the object, camera,
   or V. The UI reports whether both wall references are visible and rejects
   invalid frames. Pausing does not align a repositioned object; scan each side
   as a separate pass.
7. **Review/export** – clean the cloud, build a front-surface mesh, save the
   project, then export PLY, OBJ, or STL.

Detailed construction and calibration guidance is in
[`docs/HARDWARE_AND_CALIBRATION.md`](docs/HARDWARE_AND_CALIBRATION.md), with a
printable illustrated version in the
[calibration and corner setup guide](output/pdf/LaserLine3D_Calibration_and_Corner_Setup_Guide.pdf).
Use the exact [Test This Version procedure](docs/TESTING.md) for the first
0.2.0 hardware run. Diagnostic event and privacy coverage is recorded in the
[diagnostic coverage map](docs/DIAGNOSTIC_COVERAGE.md).

## Accuracy expectations

Accuracy depends on camera focus/resolution, calibration quality, stripe width,
surface reflectivity, the size and squareness of the corner, and camera-to-
object distance. This is a single-view scanner: it captures the visible front
surface. Rotate and scan the object from additional fixed setups if all sides
are needed; finish each side as a separate scan. Automatic multi-view
registration is intentionally not claimed in the first release. Use **Save
diagnostics ZIP...** after a problem to package the session log, settings, and
scan-quality history for troubleshooting.

## Project status

This repository begins a new project and does not reuse or modify the separate
photogrammetry implementation. See [`PROJECT_STATUS.md`](PROJECT_STATUS.md) for
the current verified baseline and remaining hardware-validation work.
