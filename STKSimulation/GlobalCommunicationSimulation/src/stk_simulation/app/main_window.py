"""SkyOps 航天综合仿真平台主窗口（双业务导航 × 双引擎切换）。"""

from __future__ import annotations

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from stk_simulation.app.pages.global_coverage_page import GlobalCoveragePage
from stk_simulation.app.pages.link_visibility_page import LinkVisibilityPage
from stk_simulation.app.simulation_controller import SimulationController
from stk_simulation.simulations.global_coverage.config import config_global_coverage
from stk_simulation.simulations.link_visibility.config import default_link_visibility_config


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("SkyOps")
        self.resize(1460, 920)
        self.setMinimumSize(1160, 740)
        self._run_mode = "normal"

        # 顶栏：双业务导航 + 右侧双引擎切换
        header = QFrame()
        header.setObjectName("topBar")
        header_layout = QHBoxLayout(header)

        self.nav_cov_btn = QPushButton("🌐 全球覆盖")
        self.nav_cov_btn.setCheckable(True)
        self.nav_cov_btn.setChecked(True)
        self.nav_link_btn = QPushButton("📡 建链可见性")
        self.nav_link_btn.setCheckable(True)

        nav_group = QButtonGroup(self)
        nav_group.setExclusive(True)
        nav_group.addButton(self.nav_cov_btn, 0)
        nav_group.addButton(self.nav_link_btn, 1)
        header_layout.addWidget(self.nav_cov_btn)
        header_layout.addWidget(self.nav_link_btn)

        header_layout.addStretch(1)

        header_layout.addWidget(QLabel("计算引擎:"))
        self.engine_combo = QComboBox()
        self.engine_combo.addItem("基于 Python", "python")
        self.engine_combo.addItem("连接 STK", "stk")
        self.engine_combo.currentIndexChanged.connect(self._on_engine_changed)
        header_layout.addWidget(self.engine_combo)

        self.stk_mode_label = QLabel("STK 会话:")
        self.stk_mode = QComboBox()
        self.stk_mode.addItem("新建 STK 实例", "new")
        self.stk_mode.addItem("连接已运行 STK", "running")
        self.connection_status = QLabel("SGP4 纯自主内核就绪")
        self.connection_status.setObjectName("connectionStatus")
        header_layout.addWidget(self.stk_mode_label)
        header_layout.addWidget(self.stk_mode)
        header_layout.addWidget(self.connection_status)

        # 多页面堆栈
        self.stack = QStackedWidget()
        self.coverage_page = GlobalCoveragePage(config_global_coverage())
        self.link_page = LinkVisibilityPage(default_link_visibility_config())
        self.stack.addWidget(self.coverage_page)
        self.stack.addWidget(self.link_page)

        self.nav_cov_btn.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        self.nav_link_btn.clicked.connect(lambda: self.stack.setCurrentIndex(1))
        self.coverage_page.run_requested.connect(
            lambda cfg, mode: self._start(cfg, mode, "global_coverage")
        )
        self.link_page.run_requested.connect(
            lambda cfg, mode: self._start(cfg, mode, "link_visibility")
        )

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addWidget(header)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(root)

        self.controller = SimulationController(self)
        self.controller.busy_changed.connect(self._set_busy)
        self.controller.completed.connect(self._show_result)
        self.controller.failed.connect(self._show_error)
        self.controller.status_changed.connect(self._on_status_changed)

        self._on_engine_changed()

    def _on_engine_changed(self) -> None:
        is_stk = self.engine_combo.currentData() == "stk"
        self.stk_mode_label.setVisible(is_stk)
        self.stk_mode.setVisible(is_stk)
        self.connection_status.setText(
            "STK 尚未连接" if is_stk else "⚡ SGP4/NumPy 引擎就绪"
        )

    def _start(self, config, run_mode: str, task_type: str) -> None:
        try:
            config.stk.engine = str(self.engine_combo.currentData())
            config.stk.mode = str(self.stk_mode.currentData())
            self._run_mode = run_mode
            self.connection_status.setText("正在计算...")
            self.controller.start(config, run_mode, task_type=task_type)
        except Exception as error:
            QMessageBox.critical(self, "无法开始仿真", str(error))

    def _on_status_changed(self, text: str) -> None:
        self.coverage_page.set_status(text)
        self.link_page.set_status(text)

    def _set_busy(self, busy: bool) -> None:
        self.engine_combo.setEnabled(not busy)
        self.stk_mode.setEnabled(not busy)
        self.coverage_page.set_busy(busy)
        self.link_page.set_busy(busy)
        if not busy:
            is_stk = self.engine_combo.currentData() == "stk"
            self.connection_status.setText("STK 已就绪" if is_stk else "⚡ SGP4/NumPy 引擎就绪")

    def _show_result(self, result, task_type: str) -> None:
        if task_type == "link_visibility":
            self.link_page.show_result(result)
        else:
            self.coverage_page.show_result(result, self._run_mode)
        self._run_mode = "normal"

    def _show_error(self, message: str) -> None:
        self._run_mode = "normal"
        self.connection_status.setText("仿真执行异常")
        QMessageBox.critical(self, "仿真错误", message)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.controller.is_busy:
            QMessageBox.information(self, "仿真进行中", "请等待当前仿真完成后再关闭程序。")
            event.ignore()
            return
        self.controller.shutdown()
        event.accept()
