"""Generate the dimensioned LaserLine 3D printable calibration PDFs."""

from __future__ import annotations

import math
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER, landscape
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "pdf"
CHECKERBOARD = OUTPUT / "LaserLine3D_Checkerboard_9x6_Inner_25mm_Letter.pdf"
GUIDE = OUTPUT / "LaserLine3D_Calibration_and_Corner_Setup_Guide.pdf"

NAVY = colors.HexColor("#17324D")
TEAL = colors.HexColor("#008C95")
PALE_TEAL = colors.HexColor("#E7F6F6")
PALE_BLUE = colors.HexColor("#EDF4FA")
AMBER = colors.HexColor("#E59D22")
PALE_AMBER = colors.HexColor("#FFF5DC")
INK = colors.HexColor("#17212B")
MUTED = colors.HexColor("#526270")
LINE = colors.HexColor("#C8D3DC")
WHITE = colors.white


def _wrap(
    pdf: canvas.Canvas,
    text: str,
    x: float,
    y: float,
    width: float,
    *,
    font: str = "Helvetica",
    size: float = 9.5,
    leading: float = 12.5,
    color: colors.Color = INK,
) -> float:
    """Draw wrapped text and return the next baseline."""
    pdf.setFont(font, size)
    pdf.setFillColor(color)
    paragraphs = text.split("\n")
    cursor = y
    for paragraph in paragraphs:
        if not paragraph:
            cursor -= leading
            continue
        words = paragraph.split()
        line = ""
        for word in words:
            candidate = word if not line else f"{line} {word}"
            if stringWidth(candidate, font, size) <= width:
                line = candidate
            else:
                pdf.drawString(x, cursor, line)
                cursor -= leading
                line = word
        if line:
            pdf.drawString(x, cursor, line)
            cursor -= leading
    return cursor


def _header(pdf: canvas.Canvas, title: str, page: int, total: int) -> None:
    width, height = LETTER
    pdf.setFillColor(NAVY)
    pdf.rect(0, height - 18 * mm, width, 18 * mm, stroke=0, fill=1)
    pdf.setFillColor(WHITE)
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(15 * mm, height - 11.5 * mm, title)
    pdf.setFont("Helvetica", 8)
    pdf.drawRightString(width - 15 * mm, height - 11.5 * mm, f"Page {page} of {total}")
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 7.5)
    pdf.drawString(15 * mm, 8 * mm, "LaserLine 3D Scanner - print guide at Actual size / 100%")


def _card(
    pdf: canvas.Canvas,
    x: float,
    y: float,
    width: float,
    height: float,
    title: str,
    fill: colors.Color = PALE_BLUE,
) -> None:
    pdf.setFillColor(fill)
    pdf.setStrokeColor(LINE)
    pdf.roundRect(x, y, width, height, 4 * mm, stroke=1, fill=1)
    pdf.setFillColor(NAVY)
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(x + 5 * mm, y + height - 8 * mm, title)


def _number(pdf: canvas.Canvas, value: int, x: float, y: float, radius: float = 4.3 * mm) -> None:
    pdf.setFillColor(AMBER)
    pdf.setStrokeColor(NAVY)
    pdf.setLineWidth(0.8)
    pdf.circle(x, y, radius, stroke=1, fill=1)
    pdf.setFillColor(NAVY)
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawCentredString(x, y - 3, str(value))


def _draw_checker_icon(pdf: canvas.Canvas, x: float, y: float, square: float = 4 * mm) -> None:
    pdf.setFillColor(WHITE)
    pdf.setStrokeColor(NAVY)
    pdf.rect(x, y, 10 * square, 7 * square, stroke=1, fill=1)
    for row in range(7):
        for col in range(10):
            if (row + col) % 2 == 0:
                pdf.setFillColor(INK)
                pdf.rect(x + col * square, y + row * square, square, square, stroke=0, fill=1)


def _draw_front_corner(
    pdf: canvas.Canvas, x: float, y: float, width: float, height: float, *, labels: bool = True
) -> None:
    top_y = y + height * 0.86
    bottom_y = y + height * 0.12
    left_top = (x, top_y)
    left_bottom = (x, bottom_y)
    hinge_top = (x + width * 0.50, top_y)
    hinge_bottom = (x + width * 0.50, bottom_y)
    right_top = (x + width, top_y)
    right_bottom = (x + width, bottom_y)
    pdf.setFillColor(PALE_BLUE)
    pdf.setStrokeColor(TEAL)
    path = pdf.beginPath()
    path.moveTo(*left_top)
    path.lineTo(*hinge_top)
    path.lineTo(*hinge_bottom)
    path.lineTo(*left_bottom)
    path.close()
    pdf.drawPath(path, stroke=1, fill=1)
    pdf.setFillColor(PALE_TEAL)
    path = pdf.beginPath()
    path.moveTo(*hinge_top)
    path.lineTo(*right_top)
    path.lineTo(*right_bottom)
    path.lineTo(*hinge_bottom)
    path.close()
    pdf.drawPath(path, stroke=1, fill=1)
    pdf.setStrokeColor(NAVY)
    pdf.setLineWidth(2)
    for start, end in (
        (left_top, left_bottom),
        (hinge_top, hinge_bottom),
        (right_top, right_bottom),
    ):
        pdf.line(*start, *end)
    if labels:
        for index, point in enumerate(
            (left_top, left_bottom, hinge_top, hinge_bottom, right_top, right_bottom), start=1
        ):
            _number(pdf, index, *point, radius=3.5 * mm)


def generate_checkerboard() -> None:
    page_width, page_height = landscape(LETTER)
    pdf = canvas.Canvas(str(CHECKERBOARD), pagesize=(page_width, page_height), pageCompression=1)
    pdf.setTitle("LaserLine 3D 9x6 Inner-Corner Checkerboard - 25 mm")
    pdf.setAuthor("LaserLine 3D Project")
    pdf.setSubject("Camera lens calibration target")

    square = 25 * mm
    columns, rows = 10, 7
    board_width, board_height = columns * square, rows * square
    origin_x = (page_width - board_width) / 2
    origin_y = (page_height - board_height) / 2

    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawCentredString(
        page_width / 2,
        page_height - 7 * mm,
        "LASERLINE 3D CAMERA LENS TARGET - 10 x 7 SQUARES / 9 x 6 INNER CORNERS / 25.00 mm",
    )
    pdf.setFont("Helvetica", 7)
    pdf.drawCentredString(
        page_width / 2,
        page_height - 11 * mm,
        "Print on US Letter landscape at Actual size / 100%. Turn off Fit, Shrink, and Scale to page.",
    )

    pdf.setFillColor(WHITE)
    pdf.rect(origin_x, origin_y, board_width, board_height, stroke=0, fill=1)
    pdf.setFillColor(colors.black)
    for row in range(rows):
        for col in range(columns):
            if (row + col) % 2 == 0:
                pdf.rect(
                    origin_x + col * square,
                    origin_y + row * square,
                    square,
                    square,
                    stroke=0,
                    fill=1,
                )

    # Independent scale checks sit in the quiet margins and do not touch the target.
    pdf.setStrokeColor(INK)
    pdf.setFillColor(INK)
    pdf.setLineWidth(0.7)
    scale = 100 * mm
    sx = (page_width - scale) / 2
    sy = 11 * mm
    pdf.line(sx, sy, sx + scale, sy)
    for offset in (0, 50 * mm, 100 * mm):
        pdf.line(sx + offset, sy - 2 * mm, sx + offset, sy + 2 * mm)
    pdf.setFont("Helvetica", 6.5)
    pdf.drawCentredString(page_width / 2, sy + 2.3 * mm, "100 mm horizontal scale check")

    vx = 10 * mm
    vy = (page_height - scale) / 2
    pdf.line(vx, vy, vx, vy + scale)
    for offset in (0, 50 * mm, 100 * mm):
        pdf.line(vx - 2 * mm, vy + offset, vx + 2 * mm, vy + offset)
    pdf.saveState()
    pdf.translate(vx + 2.5 * mm, page_height / 2)
    pdf.rotate(90)
    pdf.drawCentredString(0, 0, "100 mm vertical scale check")
    pdf.restoreState()

    pdf.showPage()
    pdf.save()


def _guide_page_one(pdf: canvas.Canvas) -> None:
    width, height = LETTER
    _header(pdf, "Calibration setup: two different physical items", 1, 4)
    y_top = height - 29 * mm
    _wrap(
        pdf,
        "The checkerboard and the scanning corner do different jobs. Do not place the checkerboard flat on the scanner base for every photo, and do not cover the scanning walls with a checkerboard pattern.",
        15 * mm,
        y_top,
        width - 30 * mm,
        font="Helvetica-Bold",
        size=11,
        leading=15,
        color=NAVY,
    )

    gap = 7 * mm
    card_width = (width - 30 * mm - gap) / 2
    card_y = 91 * mm
    card_height = 116 * mm
    left_x = 15 * mm
    right_x = left_x + card_width + gap
    _card(pdf, left_x, card_y, card_width, card_height, "A. Camera lens calibration", PALE_BLUE)
    _draw_checker_icon(pdf, left_x + 19 * mm, card_y + 69 * mm, 4 * mm)
    cursor = card_y + 62 * mm
    cursor = _wrap(
        pdf,
        "Physical item: the supplied 10 x 7 square checkerboard mounted flat to a rigid backing.",
        left_x + 6 * mm,
        cursor,
        card_width - 12 * mm,
        font="Helvetica-Bold",
        size=9,
        leading=12,
    )
    _wrap(
        pdf,
        "Purpose: measures camera lens distortion. Hold the board where the object will be. Move and tilt the board for at least 12 different photos. Keep the camera fixed.",
        left_x + 6 * mm,
        cursor - 1 * mm,
        card_width - 12 * mm,
        size=9,
        leading=12,
    )

    _card(pdf, right_x, card_y, card_width, card_height, "B. Scanning-corner calibration", PALE_TEAL)
    _draw_front_corner(pdf, right_x + 14 * mm, card_y + 69 * mm, card_width - 28 * mm, 29 * mm)
    cursor = card_y + 62 * mm
    cursor = _wrap(
        pdf,
        "Physical item: two large, rigid, plain matte-white panels joined upright as an inside V.",
        right_x + 6 * mm,
        cursor,
        card_width - 12 * mm,
        font="Helvetica-Bold",
        size=9,
        leading=12,
    )
    _wrap(
        pdf,
        "Purpose: establishes the measured 3D reference walls. With the object removed, freeze one clear view and click the six endpoints. Then place the object and capture a second view for its green scan box.",
        right_x + 6 * mm,
        cursor - 1 * mm,
        card_width - 12 * mm,
        size=9,
        leading=12,
    )

    _card(pdf, 15 * mm, 25 * mm, width - 30 * mm, 55 * mm, "Direct answers", PALE_AMBER)
    answers = [
        "Background for lens calibration: any uncluttered, non-glare room background is fine. The complete checkerboard must be visible.",
        "Background for scanning: the two V wings themselves are the reference background. Keep them plain matte white and mostly blank.",
        "Base under the object: plain matte neutral gray or white is acceptable. Avoid red, black, glossy, mirrored, or transparent material.",
        "No purchased calibration board is required. The supplied exact-scale PDF is the correct pattern for this program.",
    ]
    cursor = 68 * mm
    for answer in answers:
        pdf.setFillColor(AMBER)
        pdf.circle(21 * mm, cursor + 1.5, 1.4 * mm, stroke=0, fill=1)
        cursor = _wrap(pdf, answer, 26 * mm, cursor, width - 47 * mm, size=8.8, leading=11.5)


def _draw_pose_board(pdf: canvas.Canvas, x: float, y: float, angle: float, scale: float) -> None:
    pdf.saveState()
    pdf.translate(x, y)
    pdf.rotate(angle)
    icon_square = 3 * mm * scale
    _draw_checker_icon(pdf, -5 * icon_square, -3.5 * icon_square, icon_square)
    pdf.restoreState()


def _guide_page_two(pdf: canvas.Canvas) -> None:
    width, height = LETTER
    _header(pdf, "Step 2: calibrate the camera lens", 2, 4)
    _card(pdf, 15 * mm, height - 67 * mm, width - 30 * mm, 38 * mm, "Prepare the checkerboard", PALE_BLUE)
    cursor = height - 43 * mm
    instructions = [
        "Print the supplied checkerboard on US Letter landscape at Actual size / 100%.",
        "Measure both 100 mm scale checks. If either is wrong, correct printer scaling and print again.",
        "Mount the paper completely flat on foam board, cardboard, acrylic, or another rigid sheet.",
        "The target has 10 x 7 printed squares, which gives the program 9 x 6 inside crossings. Each square should measure 25.00 mm; enter the measured size.",
    ]
    for index, text in enumerate(instructions, start=1):
        _number(pdf, index, 23 * mm, cursor + 1.5, radius=2.7 * mm)
        cursor = _wrap(pdf, text, 30 * mm, cursor, width - 50 * mm, size=8.8, leading=11.5)
        cursor -= 2.2 * mm

    left_x = 15 * mm
    frame_y = 72 * mm
    frame_w = 105 * mm
    frame_h = 118 * mm
    pdf.setFillColor(colors.HexColor("#F8FAFC"))
    pdf.setStrokeColor(NAVY)
    pdf.roundRect(left_x, frame_y, frame_w, frame_h, 3 * mm, stroke=1, fill=1)
    pdf.setFillColor(NAVY)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(left_x + 5 * mm, frame_y + frame_h - 8 * mm, "Vary position, distance, and tilt")
    poses = [
        (left_x + 25 * mm, frame_y + 82 * mm, -13, 0.62),
        (left_x + 78 * mm, frame_y + 87 * mm, 17, 0.50),
        (left_x + 52 * mm, frame_y + 55 * mm, 0, 0.78),
        (left_x + 23 * mm, frame_y + 28 * mm, 14, 0.52),
        (left_x + 80 * mm, frame_y + 27 * mm, -18, 0.60),
    ]
    for pose in poses:
        _draw_pose_board(pdf, *pose)
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 7.5)
    pdf.drawCentredString(left_x + frame_w / 2, frame_y + 7 * mm, "The entire board stays visible and sharp in every capture.")

    right_x = 128 * mm
    pdf.setFillColor(NAVY)
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(right_x, 188 * mm, "Capture at least 12 useful views")
    bullets = [
        "Hold the board in the volume where the object will sit. Do not leave it on the floor or base for all photos.",
        "Capture the center, all four image corners, closer, farther, and several left/right/up/down tilts.",
        "Move only the checkerboard. Do not move the camera, change resolution, focus, or digital zoom.",
        "Reject cropped, blurry, strongly reflective, or nearly duplicate views.",
        "18 to 25 varied views usually gives a stronger calibration than the 12-view minimum.",
    ]
    cursor = 177 * mm
    for text in bullets:
        pdf.setFillColor(TEAL)
        pdf.circle(right_x + 1.5 * mm, cursor + 1.5, 1.3 * mm, stroke=0, fill=1)
        cursor = _wrap(pdf, text, right_x + 6 * mm, cursor, width - right_x - 21 * mm, size=9, leading=12)
        cursor -= 1.5 * mm
    _card(pdf, right_x, 75 * mm, width - right_x - 15 * mm, 38 * mm, "Good result", PALE_TEAL)
    _wrap(
        pdf,
        "Under 0.5 pixel mean reprojection error is very good. 0.5 to 1.0 pixel is generally usable. Above 1.0 pixel: clear the views and repeat with more varied, sharper poses.",
        right_x + 6 * mm,
        98 * mm,
        width - right_x - 27 * mm,
        size=8.7,
        leading=11.5,
    )


def _guide_page_three(pdf: canvas.Canvas) -> None:
    width, height = LETTER
    _header(pdf, "Step 3: build and calibrate the plain white V", 3, 4)
    _wrap(
        pdf,
        "The V is a physical scanning fixture, not another printed pattern. The camera looks into the open/concave side, like an open book standing upright. Use two images: first remove the object, turn the laser off, freeze the empty V, click six marks, and solve. Then place the object without moving the camera or V, click Capture object view for green box, and draw the box.",
        15 * mm,
        height - 29 * mm,
        width - 30 * mm,
        font="Helvetica-Bold",
        size=10.5,
        leading=14,
        color=NAVY,
    )

    _card(pdf, 15 * mm, 148 * mm, 83 * mm, 76 * mm, "Top view", PALE_TEAL)
    cx = 56.5 * mm
    hinge_y = 207 * mm
    left_end = (27 * mm, 184 * mm)
    right_end = (86 * mm, 184 * mm)
    pdf.setStrokeColor(NAVY)
    pdf.setLineWidth(4)
    pdf.line(cx, hinge_y, *left_end)
    pdf.line(cx, hinge_y, *right_end)
    pdf.setLineWidth(1)
    pdf.setStrokeColor(AMBER)
    pdf.arc(cx - 17 * mm, hinge_y - 25 * mm, cx + 17 * mm, hinge_y + 9 * mm, 225, 90)
    pdf.setFillColor(AMBER)
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawCentredString(cx, 194 * mm, "inside angle (about 90 deg)")
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 8)
    pdf.drawCentredString(cx, 176 * mm, "Measure W along each panel face")
    pdf.setFillColor(colors.HexColor("#BAC6CF"))
    pdf.circle(cx, 165 * mm, 5 * mm, stroke=1, fill=1)
    pdf.setFillColor(NAVY)
    pdf.setFont("Helvetica-Bold", 7)
    pdf.drawCentredString(cx, 163 * mm, "object")
    pdf.setStrokeColor(TEAL)
    pdf.setLineWidth(1.5)
    pdf.line(cx, 159 * mm, cx, 153 * mm)
    pdf.line(cx, 153 * mm, cx - 2 * mm, 156 * mm)
    pdf.line(cx, 153 * mm, cx + 2 * mm, 156 * mm)
    pdf.setFillColor(TEAL)
    pdf.setFont("Helvetica-Bold", 7)
    pdf.drawCentredString(cx, 149.5 * mm, "camera on open side")

    _card(pdf, 105 * mm, 148 * mm, width - 120 * mm, 76 * mm, "Build requirements", PALE_BLUE)
    requirements = [
        "Two equal-width, flat, rigid, matte-white vertical wings.",
        "Recommended calibrated area: W = 300 mm on each face and H = 400 mm vertically.",
        "One straight vertical center seam and two straight parallel outer edges.",
        "Put all three top marks at one measured height and all three bottom marks at another.",
        "Use a square/brackets and enter the real inside angle. Avoid glossy tape on the visible faces.",
        "The entered H is the exact separation between your top and bottom click marks, not an approximate panel height.",
    ]
    cursor = 207 * mm
    for text in requirements:
        pdf.setFillColor(TEAL)
        pdf.circle(112 * mm, cursor + 1, 1.2 * mm, stroke=0, fill=1)
        cursor = _wrap(pdf, text, 117 * mm, cursor, width - 137 * mm, size=8.6, leading=11.2)

    _card(pdf, 15 * mm, 39 * mm, width - 30 * mm, 98 * mm, "Front view: click these six endpoints in this exact order", PALE_AMBER)
    _draw_front_corner(pdf, 30 * mm, 55 * mm, 92 * mm, 62 * mm)
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 7.2)
    pdf.drawString(30 * mm, 47 * mm, "Top marks share one physical height; bottom marks share another.")
    labels = [
        "1  Left outer TOP",
        "2  Left outer BOTTOM",
        "3  Center seam TOP",
        "4  Center seam BOTTOM",
        "5  Right outer TOP",
        "6  Right outer BOTTOM",
    ]
    cursor = 113 * mm
    for index, label in enumerate(labels, start=1):
        pdf.setFillColor(NAVY if index in (1, 2, 5, 6) else TEAL)
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(134 * mm, cursor, label)
        cursor -= 10 * mm
def _marker(pdf: canvas.Canvas, x: float, y: float, number: int, label: str) -> None:
    size = 48 * mm
    pdf.setStrokeColor(colors.HexColor("#7D8A94"))
    pdf.setDash(3, 2)
    pdf.rect(x, y, size, size, stroke=1, fill=0)
    pdf.setDash()
    cx, cy = x + size / 2, y + size / 2 + 3 * mm
    pdf.setStrokeColor(INK)
    pdf.setLineWidth(0.7)
    pdf.circle(cx, cy, 8 * mm, stroke=1, fill=0)
    pdf.line(cx - 12 * mm, cy, cx + 12 * mm, cy)
    pdf.line(cx, cy - 12 * mm, cx, cy + 12 * mm)
    pdf.setFillColor(WHITE)
    pdf.circle(cx, cy, 4.5 * mm, stroke=1, fill=1)
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawCentredString(cx, cy - 4.3, str(number))
    pdf.setFont("Helvetica-Bold", 7.5)
    pdf.drawCentredString(cx, y + 5 * mm, label)


def _guide_page_four(pdf: canvas.Canvas) -> None:
    width, height = LETTER
    _header(pdf, "Budget fixture and optional click markers", 4, 4)
    _card(pdf, 15 * mm, 205 * mm, width - 30 * mm, 30 * mm, "Simple first fixture", PALE_TEAL)
    _wrap(
        pdf,
        "Use two white matte foam boards, rigid back supports, tape or a hinge on the rear/outside, two 90-degree brackets or a measured angle jig, a ruler/tape measure, and a fixed camera mount. Cheap craft foam board is fine for learning if it stays flat and does not move.",
        21 * mm,
        221 * mm,
        width - 42 * mm,
        size=9,
        leading=11.5,
    )
    pdf.setFillColor(NAVY)
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(15 * mm, 195 * mm, "Optional manual-click markers - cut apart on dashed lines")
    _wrap(
        pdf,
        "These are visual aids only; the software does not detect them automatically. Place each crosshair center on the exact measured endpoint. Keep them near the top/bottom boundaries, away from the laser witness stripe. Plain walls must remain visible.",
        15 * mm,
        189 * mm,
        width - 30 * mm,
        size=8.6,
        leading=11,
        color=MUTED,
    )
    markers = [
        (1, "LEFT OUTER TOP"),
        (2, "LEFT OUTER BOTTOM"),
        (3, "SEAM TOP"),
        (4, "SEAM BOTTOM"),
        (5, "RIGHT OUTER TOP"),
        (6, "RIGHT OUTER BOTTOM"),
    ]
    x_positions = [22 * mm, 82 * mm, 142 * mm]
    y_positions = [112 * mm, 50 * mm]
    for index, (number, label) in enumerate(markers):
        row, col = divmod(index, 3)
        _marker(pdf, x_positions[col], y_positions[row], number, label)

    pdf.setFillColor(PALE_AMBER)
    pdf.setStrokeColor(AMBER)
    pdf.roundRect(15 * mm, 18 * mm, width - 30 * mm, 22 * mm, 3 * mm, stroke=1, fill=1)
    _wrap(
        pdf,
        "Accuracy warning: foam board can flex. After placing the object and capturing its green scan box, do not move the camera, hinge, panels, or object. For better accuracy, upgrade later to flat PVC, MDF, or aluminum-composite panels.",
        21 * mm,
        32 * mm,
        width - 42 * mm,
        font="Helvetica-Bold",
        size=8.5,
        leading=10.5,
        color=NAVY,
    )


def generate_guide() -> None:
    pdf = canvas.Canvas(str(GUIDE), pagesize=LETTER, pageCompression=1)
    pdf.setTitle("LaserLine 3D Calibration and Corner Setup Guide")
    pdf.setAuthor("LaserLine 3D Project")
    pdf.setSubject("Printable camera calibration and reference-corner instructions")
    for draw_page in (_guide_page_one, _guide_page_two, _guide_page_three, _guide_page_four):
        draw_page(pdf)
        pdf.showPage()
    pdf.save()


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    generate_checkerboard()
    generate_guide()
    print(CHECKERBOARD)
    print(GUIDE)


if __name__ == "__main__":
    main()
