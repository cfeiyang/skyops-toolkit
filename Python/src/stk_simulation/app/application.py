"""Qt 应用创建与公共样式。"""

from __future__ import annotations

import sys

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from stk_simulation.app.main_window import MainWindow
from stk_simulation.utils.plotting import configure_chinese_font


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
    app.setApplicationName("STK 全球覆盖通信时长仿真")
    app.setStyle("Fusion")
    font_name = configure_chinese_font()
    app.setFont(QFont(font_name, 10))
    app.setStyleSheet(STYLE_SHEET)
    window = MainWindow()
    window.show()
    return app.exec()
