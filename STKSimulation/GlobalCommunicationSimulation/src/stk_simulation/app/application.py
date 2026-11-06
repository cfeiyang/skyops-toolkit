"""Qt 应用创建与公共样式。"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication

from stk_simulation.app.main_window import MainWindow
from stk_simulation.utils.plotting import configure_chinese_font


APP_ICON = Path(__file__).resolve().parents[1] / "assets" / "app_icon.ico"


STYLE_SHEET = """
QWidget {
    color: #1f2937;
    font-size: 14px;
}
QMainWindow, QWidget {
    background: #f5f7fa;
}
#topBar {
    background: white;
    border: 1px solid #dce2ea;
    border-radius: 8px;
}
#appTitle {
    font-size: 22px;
    font-weight: 600;
    color: #163a63;
}
#connectionStatus, #statusLabel, #hintLabel {
    color: #667085;
}
#gainSummary {
    background: #eef6ff;
    border: 1px solid #b9d7f5;
    border-radius: 6px;
    color: #174f7c;
    padding: 8px 12px;
}
QGroupBox {
    background: white;
    border: 1px solid #dce2ea;
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 10px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}
QTabWidget::pane, QTableWidget {
    background: white;
    border: 1px solid #dce2ea;
}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background: white;
    border: 1px solid #cbd5e1;
    border-radius: 4px;
    min-height: 30px;
    padding: 0 7px;
}
QSpinBox, QDoubleSpinBox {
    min-width: 72px;
}
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {
    background: #e2e8f0;
    border: 1px solid #cbd5e1;
    width: 20px;
}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
    background: #cbd5e1;
}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow,
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
    width: 8px;
    height: 8px;
}
QPushButton {
    background: white;
    border: 1px solid #b8c3d1;
    border-radius: 5px;
    min-height: 32px;
    padding: 0 14px;
}
QPushButton:hover {
    background: #eef4fb;
}
QPushButton:checked {
    background: #1769aa;
    color: white;
    border-color: #1769aa;
    font-weight: 600;
}
#primaryButton {
    background: #1769aa;
    color: white;
    border-color: #1769aa;
    font-weight: 600;
}
#primaryButton:hover {
    background: #125b94;
}
"""


def run_application() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("SkyOps Toolkit")
    app_icon = QIcon(str(APP_ICON))
    app.setWindowIcon(app_icon)
    app.setStyle("Fusion")
    font_name = configure_chinese_font()
    app.setFont(QFont(font_name, 10))
    app.setStyleSheet(STYLE_SHEET)
    window = MainWindow()
    window.setWindowIcon(app_icon)
    window.show()
    return app.exec()
