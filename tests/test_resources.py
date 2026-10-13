from pathlib import Path

import pytest

from laserline3d.resources import CHECKERBOARD_PDF, SETUP_GUIDE_PDF, printable_path


@pytest.mark.parametrize("filename", [CHECKERBOARD_PDF, SETUP_GUIDE_PDF])
def test_printable_pdf_is_available(filename: str) -> None:
    path = printable_path(filename)
    assert path.is_file()
    assert path.suffix.lower() == ".pdf"
    assert path.stat().st_size > 1_000


def test_printable_path_rejects_directory_traversal() -> None:
    with pytest.raises(ValueError):
        printable_path(str(Path("..") / CHECKERBOARD_PDF))
