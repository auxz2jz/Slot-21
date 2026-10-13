# Build with: python -m PyInstaller --clean --noconfirm packaging/LaserLine3D.spec

from pathlib import Path

project_root = Path(SPEC).resolve().parent.parent

a = Analysis(
    [str(project_root / "packaging" / "launcher.py")],
    pathex=[str(project_root / "src")],
    binaries=[],
    datas=[
        (
            str(
                project_root
                / "output"
                / "pdf"
                / "LaserLine3D_Calibration_and_Corner_Setup_Guide.pdf"
            ),
            "printables",
        ),
        (
            str(
                project_root
                / "output"
                / "pdf"
                / "LaserLine3D_Checkerboard_9x6_Inner_25mm_Letter.pdf"
            ),
            "printables",
        ),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "PyQt5",
        "PyQt6",
        "PySide2",
        "IPython",
        "pytest",
        "_pytest",
        "pytest_cov",
        "pytestqt",
        "coverage",
        "pygments",
    ],
    noarchive=False,
    optimize=1,
)

# The Codex build host also contains Poppler on PATH. PyInstaller can mistake
# Poppler's versioned ICU shim for the Windows system ICU interface required by
# Qt 6.12. That produces a QtCore "specified procedure could not be found"
# failure at launch. Never ship those unrelated build-host DLLs.
a.binaries = [
    item
    for item in a.binaries
    if not (
        Path(item[0]).name.lower() in {"icuuc.dll", "icudt78.dll"}
        and "poppler" in str(item[1]).lower()
    )
]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LaserLine3D",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="LaserLine3D",
)
