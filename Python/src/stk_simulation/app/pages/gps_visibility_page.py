"""GPS 可见数量功能页。"""

from __future__ import annotations

import copy
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from stk_simulation.app.widgets.plot_widget import PlotWidget
from stk_simulation.simulations.gps_visibility.config import GPSVisibilityConfig
from stk_simulation.simulations.gps_visibility.service import render_gps_visibility


class GPSVisibilityPage(QWidget):
    run_requested = Signal(object, bool)

    def __init__(self, config: GPSVisibilityConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = copy.deepcopy(config)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_scenario_tab(), "场景与卫星")
        self.tabs.addTab(self._build_link_tab(), "链路与采样")

        self.run_button = QPushButton("开始仿真")
        self.run_button.setObjectName("primaryButton")
        self.run_button.clicked.connect(self._request_run)
        self.status_label = QLabel("就绪")
        self.status_label.setObjectName("statusLabel")
        actions = QHBoxLayout()
        actions.addWidget(self.run_button)
        actions.addStretch(1)
        actions.addWidget(self.status_label)

        parameter_panel = QWidget()
        parameter_layout = QVBoxLayout(parameter_panel)
        parameter_layout.setContentsMargins(0, 0, 0, 0)
        parameter_layout.addWidget(self.tabs)
        parameter_layout.addLayout(actions)

        self.plot_widget = PlotWidget()
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(parameter_panel)
        splitter.addWidget(self.plot_widget)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([300, 560])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)
        self.write_config(config)

    def _build_scenario_tab(self) -> QWidget:
        tab = QWidget()
        self.scenario_field = QLineEdit()
        self.start_field = QLineEdit()
        self.stop_field = QLineEdit()
        scenario_form = QFormLayout()
        scenario_form.addRow("场景名称", self.scenario_field)
        scenario_form.addRow("开始时间", self.start_field)
        scenario_form.addRow("结束时间", self.stop_field)
        scenario_group = QGroupBox("场景")
        scenario_group.setLayout(scenario_form)

        self.satellite_name_field = QLineEdit()
        self.ssc_field = QSpinBox()
        self.ssc_field.setRange(1, 999999999)
        self.satellite_step_field = _double_spin(1.0, 86400.0, 1.0, 2)
        self.tle_field = QLineEdit()
        browse_button = QPushButton("浏览")
        browse_button.clicked.connect(self._browse_tle)
        tle_row = QHBoxLayout()
        tle_row.setContentsMargins(0, 0, 0, 0)
        tle_row.addWidget(self.tle_field, 1)
        tle_row.addWidget(browse_button)
        tle_host = QWidget()
        tle_host.setLayout(tle_row)
        satellite_form = QFormLayout()
        satellite_form.addRow("卫星名称", self.satellite_name_field)
        satellite_form.addRow("SSC 编号", self.ssc_field)
        satellite_form.addRow("传播步长 / s", self.satellite_step_field)
        satellite_form.addRow("TLE 文件", tle_host)
        satellite_group = QGroupBox("目标卫星")
        satellite_group.setLayout(satellite_form)

        layout = QHBoxLayout(tab)
        layout.addWidget(scenario_group, 1)
        layout.addWidget(satellite_group, 1)
        return tab

    def _build_link_tab(self) -> QWidget:
        tab = QWidget()
        self.tx_power_field = _double_spin(-300.0, 300.0, 0.1, 3)
        self.sensitivity_field = _double_spin(-300.0, 100.0, 1.0, 3)
        link_form = QFormLayout()
        link_form.addRow("GPS 发射功率 / dBW", self.tx_power_field)
        link_form.addRow("接收灵敏度 / dBW", self.sensitivity_field)
        link_group = QGroupBox("GPS 链路")
        link_group.setLayout(link_form)

        self.analysis_step_field = _double_spin(1.0, 86400.0, 1.0, 2)
        analysis_form = QFormLayout()
        analysis_form.addRow("统计采样步长 / s", self.analysis_step_field)
        analysis_group = QGroupBox("统计")
        analysis_group.setLayout(analysis_form)

        layout = QHBoxLayout(tab)
        layout.addWidget(link_group, 1)
        layout.addWidget(analysis_group, 1)
        layout.addStretch(1)
        return tab

    def read_config(self) -> GPSVisibilityConfig:
        config = copy.deepcopy(self._config)
        config.scenario.name = self.scenario_field.text().strip()
        config.scenario.start_time = self.start_field.text().strip()
        config.scenario.stop_time = self.stop_field.text().strip()
        config.satellite.name = self.satellite_name_field.text().strip()
        config.satellite.tle_file = Path(self.tle_field.text().strip())
        config.satellite.ssc = self.ssc_field.value()
        config.satellite.step = self.satellite_step_field.value()
        config.gps.tx_power = self.tx_power_field.value()
        config.receiver.sensitivity = self.sensitivity_field.value()
        config.analysis.step = self.analysis_step_field.value()
        if not config.scenario.name or not config.satellite.name:
            raise ValueError("场景名称和卫星名称不能为空。")
        if not config.satellite.tle_file.is_file():
            raise ValueError(f"TLE 文件不存在：{config.satellite.tle_file}")
        return config

    def write_config(self, config: GPSVisibilityConfig) -> None:
        self._config = copy.deepcopy(config)
        self.scenario_field.setText(config.scenario.name)
        self.start_field.setText(config.scenario.start_time)
        self.stop_field.setText(config.scenario.stop_time)
        self.satellite_name_field.setText(config.satellite.name)
        self.tle_field.setText(str(config.satellite.tle_file))
        self.ssc_field.setValue(config.satellite.ssc)
        self.satellite_step_field.setValue(config.satellite.step)
        self.tx_power_field.setValue(config.gps.tx_power)
        self.sensitivity_field.setValue(config.receiver.sensitivity)
        self.analysis_step_field.setValue(config.analysis.step)

    def apply_stk_mode(self, mode: str) -> GPSVisibilityConfig:
        config = self.read_config()
        config.stk.mode = mode
        return config

    def set_busy(self, busy: bool) -> None:
        self.run_button.setEnabled(not busy)
        self.tabs.setEnabled(not busy)
        self.plot_widget.set_busy(busy)

    def set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def show_result(self, result) -> None:
        self.plot_widget.show_result(result, render_gps_visibility)
        self.set_status(f"完成 · {result.output.image_path}")

    def _request_run(self) -> None:
        try:
            config = self.read_config()
        except Exception as error:
            QMessageBox.critical(self, "参数错误", str(error))
            return
        self.set_status("准备连接 STK...")
        self.run_requested.emit(config, False)

    def _browse_tle(self) -> None:
        current = Path(self.tle_field.text())
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "选择目标卫星 TLE",
            str(current.parent),
            "TLE 文件 (*.txt *.tle);;全部文件 (*.*)",
        )
        if selected:
            self.tle_field.setText(selected)


def _double_spin(
    minimum: float, maximum: float, step: float, decimals: int
) -> QDoubleSpinBox:
    field = QDoubleSpinBox()
    field.setRange(minimum, maximum)
    field.setSingleStep(step)
    field.setDecimals(decimals)
    return field
