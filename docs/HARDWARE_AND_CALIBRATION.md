# Hardware and calibration guide

## What to build

LaserLine 3D uses a rigid vertical reference corner. Two flat panels meet at a
vertical hinge and open toward the camera:

```text
Top view (not to scale)

          hinge
            V
 left wing / \ right wing
           [object]

             camera
```

Recommended first rig:

- two matte-white foam-board, PVC, or MDF panels;
- 300 mm measured surface width per wing;
- 400 mm or greater usable height;
- a 90 degree inside angle held by rigid brackets;
- dark/non-red surroundings and no glossy tape in the witness areas;
- camera on a tripod or rigid mount, approximately centred on the hinge;
- object centred in front of the hinge with a clear strip of each wing visible.

The software accepts other measured widths and an inside angle from 30 to 150
degrees. Metric accuracy depends directly on those measurements. A nominal
cardboard fold is not necessarily exactly 90 degrees; use a square or measure
the actual angle.

## The three laser segments every frame needs

The same projected sheet of light must create a stripe on:

1. the clear part of the left wing;
2. the object;
3. the clear part of the right wing.

The two wall segments are witnesses. Their known geometry tells the program
the position and angle of the handheld laser sheet for that frame. If either
one is missing, that frame is rejected. The program never reuses the previous
frame's plane.

Keep the laser stripe approximately horizontal and sweep it vertically. Move
slowly or pause at short intervals. Most consumer Logitech cameras use rolling
shutters; fast laser motion can bend the witness stripe because different image
rows are exposed at different times.

## Camera placement

- The entire usable corner and both outer edges must fit in the image.
- Fill as much of the frame as practical; excess distance reduces precision.
- Avoid extreme wide-angle zoom settings.
- Lock focus, exposure, gain, and white balance when the driver supports it.
- A narrow 2–6 pixel stripe is preferable to a saturated glowing band.
- Do not bump the camera or corner after corner calibration. Place the object
  only when the program asks for the second object image, then do not move it.
- Camera calibration is valid only at the exact captured resolution and crop.

The DirectShow backend usually exposes Logitech controls most consistently.
Media Foundation is included as a fallback.

### Camera controls that actually help

Open **Camera driver settings...** before lens calibration. When the camera and
driver provide the controls, turn off autofocus, auto exposure, and automatic
white balance, then set:

- focus once, so the object and both reference wings are sharp;
- exposure low enough that the laser is a narrow red line instead of a wide
  white/red glow;
- gain as low as practical, because high gain creates colored speckle;
- white balance once, then leave it fixed.

Brightness, contrast, saturation, and sharpness are image-processing controls,
not substitutes for correct exposure. High sharpness can add false edges around
the laser. Camera property ranges and even availability are driver-specific, so
the application reports what the driver returns but does not pretend every
camera accepts the same slider scale.

Most webcams have a fixed lens and no optical zoom. A driver "Zoom" control is
usually a digital crop: it throws away field of view and does not add measured
detail. If the whole V does not fit, use the highest clean camera resolution, a
wider-field lens/camera, or a smaller V/object setup. Any change to focus,
resolution, crop, digital zoom, or camera position invalidates the lens and
corner calibrations; calibrate again afterward.

## Printable files and backgrounds

- Print the supplied
  [`LaserLine3D_Checkerboard_9x6_Inner_25mm_Letter.pdf`](../output/pdf/LaserLine3D_Checkerboard_9x6_Inner_25mm_Letter.pdf)
  on US Letter paper in landscape orientation at **Actual size / 100%**. Turn
  off Fit, Shrink, and Scale to page. Measure both 100 mm scale checks before
  using it.
- Mount the print completely flat on foam board, cardboard, acrylic, or another
  rigid sheet. A curled or flexible page changes the calibration geometry.
- The printable
  [`LaserLine3D_Calibration_and_Corner_Setup_Guide.pdf`](../output/pdf/LaserLine3D_Calibration_and_Corner_Setup_Guide.pdf)
  includes fixture diagrams and optional cut-apart click markers.
- Lens calibration needs no special room background—use an uncluttered,
  non-glare background and keep the whole checkerboard visible.
- The scanning background is the two **plain matte-white V wings**. Do not add a
  checkerboard or repeating pattern to them. A plain matte neutral-gray or
  white base is suitable; avoid red, black, glossy, mirrored, or transparent
  surfaces.

## Checkerboard lens calibration

The defaults expect 9 by 6 **inner intersections**, not printed squares. If a
board has 10 by 7 squares, it has 9 by 6 inner corners. Measure one printed
square with a ruler or caliper and enter that size in millimetres.

Capture at least 12 views; 18–25 is better. Cover:

- image centre and all four corners;
- near and far distances;
- left, right, upward, and downward tilts.

Hold the board in the volume where the object will sit. Move and tilt the board
between captures; do not leave it flat on the base for every photo. Keep the
camera, focus, resolution, and digital zoom fixed.

Avoid blur, glare, cropped corners, and many nearly identical views. A mean
reprojection error under 0.5 px is very good, 0.5–1.0 px is generally usable,
and above 1.0 px merits another calibration.

## Reference-corner landmarks

The V is a separate physical fixture, not another printed target. Make both
wings the same measured width. Measure width along each panel face from the
center seam to its outer edge. Put the three top marks at one physical height,
the three bottom marks at another, and enter the exact top-to-bottom mark
separation as the height.

Use this two-image sequence:

1. Remove the object and turn the laser off.
2. Enter the actual equal wing width, inside angle, and marked height.
3. Freeze the empty V with all three marked vertical edges visible.
4. Click these six points in exact order:

   1. left outer top;
   2. left outer bottom;
   3. center seam top;
   4. center seam bottom;
   5. right outer top;
   6. right outer bottom.

5. Solve the corner pose.
6. Place the object without moving the camera or V.
7. Click **Capture object view for green box** to take a fresh image.
8. Drag the green box tightly around only the object. Leave substantial wall
   area outside it on both sides for the laser witness stripe, then save.

Use the **Zoom in**, **Zoom out**, and **Fit image** buttons or the mouse wheel;
right-drag pans and left-click places a point. The optional numbered markers in
the printable guide are visual click aids only—the software does not detect
them automatically.

## Laser-off background and tuning

Leave the overhead/room lighting **on at the exact level you will use while
scanning**. Diffuse, steady room light is usually easier to work with than a
dark room. It is also valid to scan with the room lights off, but only if they
remain off for both the background capture and every scan frame. Do not change
lighting or camera controls after the background is captured.

Put the object in its final position, keep the camera and scene still, turn only
the red line laser off, and capture the 15-frame background. Averaging 15 frames
reduces camera noise. Then turn the laser on without moving anything. The three
tuning values mean:

- **Minimum red brightness** (default 120): how bright the red camera channel
  must be. Raise it to reject dim reddish noise; lower it if the real stripe is
  being lost on a dark surface.
- **Red over other colors** (default 45): how much stronger red must be than
  green or blue. Raise it to reject white/orange highlights and neutral light;
  lower it for a washed-out but genuine red stripe.
- **Change from laser-off background** (default 55): how much the pixel must
  change from the saved laser-off scene. Raise it to remove unchanged clutter
  and weak flicker; lower it if the real stripe is too faint.

Use **Auto-suggest from laser-on view** as a starting point, not as a guarantee,
and use **Restore defaults** whenever manual tuning becomes confusing. The goal
is one thin, continuous detected trace on the left wall, object, and right wall,
with very few isolated dots. The dashed cyan outlines identify the two wall
reference regions and the dashed green rectangle identifies the object region;
they are not laser detections. Detected wall samples are cyan and detected
object samples are green.

If the trace is a thick glow or the saturation reading is high, reduce exposure
or gain in the camera driver, reduce laser power if safely adjustable, refocus
the line-laser optic, increase laser distance, and avoid glossy surfaces. Do not
try to cure optical bloom with high software sharpness. If the live scene is
brighter or darker than the saved background, restore the original lighting and
camera settings or recapture the background.

## Surfaces that need preparation

Dark, glossy, mirror-like, translucent, and red objects may produce missing or
false laser detections. For measurement work, apply a removable matte scanning
spray or another safe non-red diffuse coating when the object permits it.

## Laser safety

The software cannot make a laser safe. Identify the laser class and wavelength,
follow its manufacturer instructions, use wavelength/class-appropriate eye
protection, control reflections, keep the beam below eye level, and exclude
unprotected people and animals from the scan area. Never look into the source
or point it toward a camera operator.

## What one pass measures

One fixed-camera pass measures the surface visible to that camera. It cannot see
the back, deep occluded recesses, or undersides. OBJ/STL export is therefore an
open measured surface, not a guaranteed watertight CAD solid. A future indexed
turntable workflow is the appropriate way to capture and register multiple sides.

The object must remain stationary from the object-area capture through the end
of a scan. Pausing protects the points already collected, but it does not give
the software a way to measure a rotation or translation. Rotating the object
and resuming in the same scan therefore produces doubled or misplaced geometry;
moving it while scanning is worse. For another side, finish/export the current
pass, reposition the object, capture a new object area and laser-off background,
then start a separate scan. Merge those scans later only with an alignment tool
or a future indexed-turntable workflow.

## Diagnostics for support

The application records timestamped camera, calibration, tuning, button, scan,
quality, and failure events for the current session. Use **Save diagnostics
ZIP...** to make one uploadable support file containing that log and a machine-
readable summary. The save dialog explains whether camera images are included;
review the ZIP before sharing it if the scene is private. The log records slider
values and scan rejection reasons so a failed session can be diagnosed without
guessing what happened on screen.
