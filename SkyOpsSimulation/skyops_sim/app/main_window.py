"""SkyOps 仿真桌面应用的导航与任务协调。"""

from __future__ import annotations

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QButtonGroup, QDialog, QFrame, QHBoxLayout, QMainWindow,
    QMessageBox, QStackedWidget, QVBoxLayout, QWidget,
)

from skyops_sim.app.dialogs.satellite_settings import (
    SatelliteSettingsDialog, load_reference_satellite, save_reference_satellite,
)
from skyops_sim.app.icons import action_button
from skyops_sim.app.pages.global_coverage_page import GlobalCoveragePage
from skyops_sim.app.pages.link_visibility_page import LinkVisibilityPage
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
        self._active_page = self.coverage_page
        for page in (self.coverage_page, self.link_page):
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
        )):
            button = action_button(title, artwork)
            button.setObjectName("navButton")
            button.setCheckable(True)
            nav_group.addButton(button, index)
            header_layout.addWidget(button)
        nav_group.button(0).setChecked(True)
        nav_group.idClicked.connect(self.stack.setCurrentIndex)
        header_layout.addStretch(1)

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
        self.link_page.stk_file_requested.connect(self._start_stk_file)
        self.controller.stk_file_saved.connect(
            lambda path: self.link_page.set_status(f"已保存至 {path}")
        )

    def _set_reference_satellite(self, profile) -> None:
        self._reference_satellite = profile
        self.coverage_page.set_reference_satellite(profile)
        self.link_page.set_reference_satellite(profile)
        self.satellite_settings.setText(f"卫星设置 · {profile.name}")
        source = "本地 TLE" if profile.tle_file else "TLE 在线更新"
        self.satellite_settings.setToolTip(f"{profile.label}\n{source}")

    def _edit_satellite(self) -> None:
        dialog = SatelliteSettingsDialog(self._reference_satellite, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._set_reference_satellite(dialog.profile)
            save_reference_satellite(dialog.profile)

    def _start(self, config, run_mode: str, task_type: str) -> None:
        if self.controller.is_busy:
            return
        try:
            self._run_mode = run_mode
            self._active_page = self.link_page if task_type == "link_visibility" else self.coverage_page
            self.controller.start(config, run_mode, task_type=task_type)
        except Exception as error:
            self._show_error(str(error))

    def _start_stk_file(self, action: str, path: str, scenario: str) -> None:
        if self.controller.is_busy:
            return
        self._active_page = self.link_page
        try:
            self.controller.save_stk_file(action, path, scenario)
        except Exception as error:
            self._show_error(str(error))

    def _on_status_changed(self, text: str) -> None:
        self._active_page.set_status(text)

    def _set_simulation_busy(self, busy: bool) -> None:
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
        self._active_page.set_status(message.splitlines()[0] if message else "操作失败")
        QMessageBox.warning(self, "操作未完成", message)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.controller.is_busy:
            QMessageBox.information(self, "操作进行中", "请等待当前操作完成后再关闭。")
            event.ignore()
            return
        self.controller.shutdown()
        event.accept()
