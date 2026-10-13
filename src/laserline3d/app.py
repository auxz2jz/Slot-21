from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import __version__
from .diagnostics import DiagnosticLog, install_exception_hook


def _arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LaserLine 3D scanner")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run a deterministic no-camera reconstruction and export test",
    )
    parser.add_argument(
        "--self-test-output",
        type=Path,
        help="Keep self-test PLY/STL outputs in this directory",
    )
    parser.add_argument(
        "--qt-smoke-test",
        action="store_true",
        help="Construct the real Qt main window, write a report, and exit",
    )
    parser.add_argument(
        "--qt-smoke-output",
        type=Path,
        help="JSON report written by --qt-smoke-test",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _arguments(argv)
    if args.self_test:
        from .self_test import run_self_test

        try:
            print(json.dumps(run_self_test(args.self_test_output), indent=2))
            return 0
        except Exception as error:
            print(json.dumps({"status": "failed", "error": str(error)}, indent=2), file=sys.stderr)
            return 1

    from PySide6.QtCore import QCoreApplication, qVersion
    from PySide6.QtWidgets import QApplication

    QCoreApplication.setOrganizationName("LaserLine3D")
    QCoreApplication.setApplicationName("LaserLine 3D Scanner")
    application = QApplication(sys.argv if argv is None else [sys.argv[0], *argv])
    application.setStyle("Fusion")
    application.setStyleSheet(STYLE_SHEET)
    diagnostics = DiagnosticLog(app_version=__version__)
    install_exception_hook(diagnostics)
    from .ui.main_window import MainWindow

    window = MainWindow(diagnostics)
    window.show()
    if args.qt_smoke_test:
        application.processEvents()
        from .resources import CHECKERBOARD_PDF, SETUP_GUIDE_PDF, printable_path

        report = {
            "status": "passed",
            "application_version": __version__,
            "window_title": window.windowTitle(),
            "workflow_pages": window.stack.count(),
            "qt_version": qVersion(),
            "printables": {
                "checkerboard": printable_path(CHECKERBOARD_PDF).is_file(),
                "setup_guide": printable_path(SETUP_GUIDE_PDF).is_file(),
            },
        }
        if args.qt_smoke_output is not None:
            args.qt_smoke_output.parent.mkdir(parents=True, exist_ok=True)
            args.qt_smoke_output.write_text(
                json.dumps(report, indent=2) + "\n", encoding="utf-8"
            )
        window.close()
        application.processEvents()
        return 0
    return application.exec()


STYLE_SHEET = r"""
QWidget {
  background: #151b24;
  color: #edf2f7;
  font-family: "Segoe UI";
  font-size: 10.5pt;
}
QMainWindow { background: #151b24; }
#workflowNavigation {
  background: #0d1219;
  border: none;
  padding: 18px 8px;
  outline: 0;
}
#workflowNavigation::item {
  color: #9eabba;
  border-radius: 7px;
  padding: 10px 12px;
  margin: 2px 5px;
}
#workflowNavigation::item:selected {
  background: #23364d;
  color: #72c8ff;
}
#pageTitle { font-size: 24pt; font-weight: 650; color: white; }
#pageDescription { color: #a9b6c7; font-size: 11pt; }
#panel, #statusCard, #notice {
  background: #1d2632;
  border: 1px solid #2c394a;
  border-radius: 9px;
}
#notice { border-left: 4px solid #5bbcf6; }
#cardTitle { color: #aab7c8; font-size: 9.5pt; font-weight: 600; }
#safetyText { color: #ffd166; }
#fieldHelp { color: #a9b6c7; font-size: 9pt; }
#guidance {
  background: #202a37;
  border-radius: 7px;
  padding: 11px;
  color: #ffd166;
  font-size: 11pt;
}
#guidance[accepted="true"] { color: #73e493; }
QPushButton {
  background: #273445;
  border: 1px solid #3a4a5e;
  border-radius: 6px;
  padding: 8px 13px;
}
QPushButton:hover { background: #324258; }
QPushButton:pressed { background: #1f2b3a; }
QPushButton:disabled { color: #667487; background: #1b232e; }
#primaryButton {
  background: #1579b8;
  border-color: #2b98da;
  font-weight: 600;
}
#primaryButton:hover { background: #1b8dcc; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
  background: #101720;
  border: 1px solid #37465a;
  border-radius: 5px;
  padding: 6px;
}
QSlider::groove:horizontal { height: 5px; background: #344154; border-radius: 2px; }
QSlider::handle:horizontal { width: 15px; margin: -5px 0; background: #5cc2ff; border-radius: 7px; }
QToolTip { background: #202a36; color: white; border: 1px solid #4b5d73; }
"""


if __name__ == "__main__":
    raise SystemExit(main())
