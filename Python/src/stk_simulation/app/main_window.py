"""全球覆盖通信时长仿真主窗口。"""

from __future__ import annotations

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from stk_simulation.app.pages.global_coverage_page import GlobalCoveragePage
from stk_simulation.app.simulation_controller import SimulationController
from stk_simulation.simulations.global_coverage.config import config_global_coverage


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("STK 全球覆盖通信时长仿真")
        self.resize(1420, 900)
        self.setMinimumSize(1120, 720)
        self._document_scenarios_requested = False

        self.stk_mode = QComboBox()
        self.stk_mode.addItem("新建 STK", "new")
        self.stk_mode.addItem("连接已运行 STK", "running")
        self.connection_status = QLabel("STK 尚未连接")
        self.connection_status.setObjectName("connectionStatus")

        header = QFrame()
        header.setObjectName("topBar")
        header_layout = QHBoxLayout(header)
        title = QLabel("STK 全球覆盖通信时长仿真")
        title.setObjectName("appTitle")
        header_layout.addWidget(title)
        header_layout.addStretch(1)
        header_layout.addWidget(QLabel("STK 连接"))
        header_layout.addWidget(self.stk_mode)
        header_layout.addWidget(self.connection_status)

        self.page = GlobalCoveragePage(config_global_coverage())
        self.page.run_requested.connect(self._start)

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addWidget(header)
        layout.addWidget(self.page, 1)
        self.setCentralWidget(root)

        self.controller = SimulationController(self)
        self.controller.busy_changed.connect(self._set_busy)
        self.controller.completed.connect(self._show_result)
        self.controller.failed.connect(self._show_error)
        self.controller.status_changed.connect(self.page.set_status)

    def _start(self, config, document_scenarios: bool) -> None:
        try:
            config.stk.mode = str(self.stk_mode.currentData())
            self._document_scenarios_requested = document_scenarios
            self.connection_status.setText("正在连接或计算...")
            self.controller.start(config, document_scenarios)
        except Exception as error:
            QMessageBox.critical(self, "无法开始仿真", str(error))

    def _set_busy(self, busy: bool) -> None:
        self.stk_mode.setEnabled(not busy)
        self.page.set_busy(busy)
        if not busy:
            self.connection_status.setText("STK 已连接")

    def _show_result(self, result) -> None:
        self.page.show_result(result, self._document_scenarios_requested)
        self._document_scenarios_requested = False

    def _show_error(self, message: str) -> None:
        self._document_scenarios_requested = False
        self.connection_status.setText("STK 连接或仿真失败")
        self.page.set_status("仿真失败")
        QMessageBox.critical(self, "仿真错误", message)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.controller.is_busy:
            QMessageBox.information(
                self, "仿真进行中", "请等待当前仿真完成后再关闭程序。"
            )
            event.ignore()
            return
        self.controller.shutdown()
        event.accept()
