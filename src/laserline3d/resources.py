"""Locations for bundled and source-tree user resources."""

from __future__ import annotations

import sys
from pathlib import Path


CHECKERBOARD_PDF = "LaserLine3D_Checkerboard_9x6_Inner_25mm_Letter.pdf"
SETUP_GUIDE_PDF = "LaserLine3D_Calibration_and_Corner_Setup_Guide.pdf"


def printable_path(filename: str) -> Path:
    """Return a printable PDF path in source or frozen application layouts."""
    if Path(filename).name != filename:
        raise ValueError("Printable resource names cannot contain directories")

    candidates: list[Path] = []
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        candidates.append(Path(bundle_root) / "printables" / filename)
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / "printables" / filename)

    project_root = Path(__file__).resolve().parents[2]
    candidates.extend(
        (
            project_root / "output" / "pdf" / filename,
            Path.cwd() / "output" / "pdf" / filename,
        )
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return candidates[0]
