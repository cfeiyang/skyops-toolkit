"""统一承载全部仿真功能的主窗口。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from stk_simulation.app.feature_registry import FEATURES
from stk_simulation.app.simulation_controller import SimulationController


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("STK 卫星通信仿真")
        self.resize(1480, 900)
        self.setMinimumSize(1180, 720)

        self.controller = SimulationController(self)
        self.pages: dict[str, QWidget] = {}
        self._batch_requests: dict[str, bool] = {}

        self.stk_mode = QComboBox()
        self.stk_mode.addItem("新建 STK", "new")
        self.stk_mode.addItem("连接已运行 STK", "running")
        self.connection_status = QLabel("STK 尚未连接")
        self.connection_status.setObjectName("connectionStatus")

        header = QFrame()
        header.setObjectName("topBar")
        header_layout = QHBoxLayout(header)
        title = QLabel("STK 卫星通信仿真")
        title.setObjectName("appTitle")
        header_layout.addWidget(title)
        header_layout.addStretch(1)
        header_layout.addWidget(QLabel("STK 连接"))
        header_layout.addWidget(self.stk_mode)
        header_layout.addWidget(self.connection_status)

        self.navigation = QListWidget()
        self.navigation.setObjectName("navigation")
        self.navigation.setFixedWidth(210)
        self.navigation.setSpacing(3)
        self.stack = QStackedWidget()
        for feature in FEATURES:
            item = QListWidgetItem(feature.title)
            item.setToolTip(feature.description)
            item.setData(Qt.ItemDataRole.UserRole, feature.key)
            self.navigation.addItem(item)
            page = feature.page_type(feature.config_factory())
            page.run_requested.connect(
                lambda config, batch, key=feature.key: self._start(key, config, batch)
            )
            self.pages[feature.key] = page
            self.stack.addWidget(page)
        self.navigation.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.navigation.setCurrentRow(0)

        content = QHBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.addWidget(self.navigation)
        content.addWidget(self.stack, 1)
        content_host = QWidget()
        content_host.setLayout(content)

        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.addWidget(header)
        root_layout.addWidget(content_host, 1)
        self.setCentralWidget(root)

        self.controller.busy_changed.connect(self._set_busy)
        self.controller.completed.connect(self._show_result)
        self.controller.failed.connect(self._show_error)
        self.controller.status_changed.connect(self._show_status)

    def _start(self, feature_key: str, config, batch: bool) -> None:
        try:
            config.stk.mode = str(self.stk_mode.currentData())
            self._batch_requests[feature_key] = batch
            self.connection_status.setText("正在连接或计算...")
            self.controller.start(feature_key, config, batch)
        except Exception as error:
            QMessageBox.critical(self, "无法开始仿真", str(error))

    def _set_busy(self, busy: bool) -> None:
        self.stk_mode.setEnabled(not busy)
        for page in self.pages.values():
            page.set_busy(busy)
        if not busy:
            self.connection_status.setText("STK 已连接")

    def _show_result(self, feature_key: str, result) -> None:
        page = self.pages[feature_key]
        if feature_key == "global_coverage":
            page.show_result(result, self._batch_requests.pop(feature_key, False))
        else:
            page.show_result(result)

    def _show_error(self, feature_key: str, message: str) -> None:
        self._batch_requests.pop(feature_key, None)
        self.connection_status.setText("STK 连接或仿真失败")
        self.pages[feature_key].set_status("仿真失败")
        QMessageBox.critical(self, "仿真错误", message)

    def _show_status(self, feature_key: str, message: str) -> None:
        self.pages[feature_key].set_status(message)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.controller.is_busy:
            QMessageBox.information(self, "仿真进行中", "请等待当前仿真完成后再关闭程序。")
            event.ignore()
            return
        self.controller.shutdown()
        event.accept()
