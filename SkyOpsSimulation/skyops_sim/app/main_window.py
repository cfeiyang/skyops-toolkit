"""SkyOps 仿真桌面应用的导航与任务协调。"""

from __future__ import annotations

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QButtonGroup, QComboBox, QDialog, QFrame, QHBoxLayout, QLabel, QMainWindow,
    QMessageBox, QStackedWidget, QVBoxLayout, QWidget,
)

from skyops_sim.app.dialogs.satellite_settings import (
    SatelliteSettingsDialog, load_reference_satellite, save_reference_satellite,
)
from skyops_sim.app.icons import action_button
from skyops_sim.app.pages.global_coverage_page import GlobalCoveragePage
from skyops_sim.app.pages.link_visibility_page import LinkVisibilityPage
from skyops_sim.app.pages.workbench_page import WorkbenchPage
from skyops_sim.app.simulation_controller import SimulationController
from skyops_sim.simulations.global_coverage.config import config_global_coverage
from skyops_sim.simulations.link_visibility.config import default_link_visibility_config


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("SkyOps")
        self.resize(1360, 870)
        self.setMinimumSize(1160, 740)
        self._run_mode = "normal"

        self.stack = QStackedWidget()
        self.coverage_page = GlobalCoveragePage(config_global_coverage())
        self.link_page = LinkVisibilityPage(default_link_visibility_config())
        self.workbench_page = WorkbenchPage()
        for page in (self.coverage_page, self.link_page, self.workbench_page):
            self.stack.addWidget(page)

        header = QFrame()
        header.setObjectName("topBar")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(10, 7, 12, 7)
        header_layout.setSpacing(6)
        nav_group = QButtonGroup(self)
        nav_group.setExclusive(True)
        for index, (title, artwork) in enumerate((
            ("全球覆盖", "globe"),
            ("建链可见性", "radio-tower"),
            ("STK 工作台", "satellite"),
        )):
            button = action_button(title, artwork)
            button.setObjectName("navButton")
            button.setCheckable(True)
            nav_group.addButton(button, index)
            header_layout.addWidget(button)
        nav_group.button(0).setChecked(True)
        nav_group.idClicked.connect(self.stack.setCurrentIndex)
        header_layout.addStretch(1)

        self.header_controls = QStackedWidget()
        self.header_controls.addWidget(self._engine_controls())
        self.header_controls.addWidget(self.workbench_page.connection_controls)
        self.stack.currentChanged.connect(self._show_header_controls)
        header_layout.addWidget(self.header_controls)
        self.satellite_settings = action_button("卫星设置", "orbit")
        self.satellite_settings.clicked.connect(self._edit_satellite)
        header_layout.addWidget(self.satellite_settings)
        self._set_reference_satellite(load_reference_satellite())

        self.coverage_page.run_requested.connect(
            lambda cfg, mode: self._start(cfg, mode, "global_coverage")
        )
        self.link_page.run_requested.connect(
            lambda cfg, mode: self._start(cfg, mode, "link_visibility")
        )

        root = QWidget()
        root.setObjectName("appRoot")
        layout = QVBoxLayout(root)
        layout.setContentsMargins(12, 11, 12, 12)
        layout.setSpacing(11)
        layout.addWidget(header)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(root)

        self.controller = SimulationController(self)
        self.controller.busy_changed.connect(self._set_simulation_busy)
        self.controller.completed.connect(self._show_result)
        self.controller.failed.connect(self._show_error)
        self.controller.status_changed.connect(self._on_status_changed)
        self.workbench_page.busy_changed.connect(self._refresh_task_controls)
        self._on_engine_changed()

    def _set_reference_satellite(self, profile) -> None:
        self._reference_satellite = profile
        self.coverage_page.set_reference_satellite(profile)
        self.link_page.set_reference_satellite(profile)
        self.workbench_page.set_reference_satellite(profile)
        self.satellite_settings.setText(f"卫星设置 · {profile.name}")
        source = "本地 TLE" if profile.tle_file else "TLE 在线更新"
        self.satellite_settings.setToolTip(f"{profile.label}\n{source}")

    def _edit_satellite(self) -> None:
        dialog = SatelliteSettingsDialog(self._reference_satellite, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._set_reference_satellite(dialog.profile)
            save_reference_satellite(dialog.profile)

    def _engine_controls(self) -> QWidget:
        widget = QWidget()
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addStretch(1)
        row.addWidget(QLabel("计算引擎"))
        self.engine_combo = QComboBox()
        self.engine_combo.addItem("基于 Python", "python")
        self.engine_combo.addItem("连接 STK", "stk")
        self.engine_combo.currentIndexChanged.connect(self._on_engine_changed)
        row.addWidget(self.engine_combo)

        self.stk_mode_label = QLabel("STK 会话")
        self.stk_mode = QComboBox()
        self.stk_mode.addItem("新建 STK 实例", "new")
        self.stk_mode.addItem("连接已运行 STK", "running")
        self.connection_status = QLabel()
        self.connection_status.setObjectName("connectionStatus")
        row.addWidget(self.stk_mode_label)
        row.addWidget(self.stk_mode)
        row.addWidget(self.connection_status)
        return widget

    def _show_header_controls(self, _index: int) -> None:
        is_workbench = self.stack.currentWidget() is self.workbench_page
        self.header_controls.setCurrentIndex(1 if is_workbench else 0)

    def _on_engine_changed(self) -> None:
        is_stk = self.engine_combo.currentData() == "stk"
        self.stk_mode_label.setVisible(is_stk)
        self.stk_mode.setVisible(is_stk)
        self.connection_status.setText("STK 尚未连接" if is_stk else "Python 引擎就绪")

    def _start(self, config, run_mode: str, task_type: str) -> None:
        if self.workbench_page.is_busy:
            return
        try:
            config.stk.engine = str(self.engine_combo.currentData())
            config.stk.mode = str(self.stk_mode.currentData())
            self._run_mode = run_mode
            self.connection_status.setText("正在计算…")
            self.controller.start(config, run_mode, task_type=task_type)
        except Exception as error:
            QMessageBox.critical(self, "无法开始仿真", str(error))

    def _on_status_changed(self, text: str) -> None:
        self.coverage_page.set_status(text)
        self.link_page.set_status(text)

    def _set_simulation_busy(self, busy: bool) -> None:
        self.workbench_page.set_simulation_busy(busy)
        self._refresh_task_controls()
        if not busy:
            is_stk = self.engine_combo.currentData() == "stk"
            self.connection_status.setText("STK 已就绪" if is_stk else "Python 引擎就绪")

    def _refresh_task_controls(self) -> None:
        busy = self.controller.is_busy or self.workbench_page.is_busy
        self.engine_combo.setEnabled(not busy)
        self.stk_mode.setEnabled(not busy)
        self.satellite_settings.setEnabled(not busy)
        self.coverage_page.set_busy(busy)
        self.link_page.set_busy(busy)

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
        if self.controller.is_busy or self.workbench_page.is_busy:
            QMessageBox.information(self, "操作进行中", "请等待当前操作完成后再关闭。")
            event.ignore()
            return
        self.controller.shutdown()
        event.accept()
