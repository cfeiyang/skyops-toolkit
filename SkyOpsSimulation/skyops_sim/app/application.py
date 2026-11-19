"""Qt 应用创建与公共样式。"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication

from skyops_sim.app.main_window import MainWindow
from skyops_sim.utils.plotting import configure_chinese_font


ASSETS = Path(__file__).resolve().parents[1] / "assets"


def run_application() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("SkyOps")
    app_icon = QIcon(str(ASSETS / "app_icon.ico"))
    app.setWindowIcon(app_icon)
    app.setStyle("Fusion")
    font_name = configure_chinese_font()
    app.setFont(QFont(font_name, 10))
    stylesheet = (ASSETS / "skyops.qss").read_text(encoding="utf-8")
    app.setStyleSheet(stylesheet.replace("@icons@", (ASSETS / "icons").as_posix()))
    window = MainWindow()
    window.setWindowIcon(app_icon)
    window.show()
    return app.exec()
