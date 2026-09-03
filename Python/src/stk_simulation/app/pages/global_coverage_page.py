"""全球通信时长功能页。"""

from __future__ import annotations

import copy
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from stk_simulation.app.dialogs.station_dialog import StationDialog
from stk_simulation.app.widgets.plot_widget import PlotWidget
from stk_simulation.simulations.global_coverage.config import GlobalCoverageConfig
from stk_simulation.simulations.global_coverage.presets import (
    StationConfig,
    station_template,
)


SATELLITE_MODES = (("单星", "single"), ("三星几何星间中继", "multi"))
STATION_PRESETS = (
    ("上海临港单站", "single"),
    ("四个国内基本站", "domestic"),
    ("五站（含墨西哥）", "all"),
)


class GlobalCoveragePage(QWidget):
    run_requested = Signal(object, bool)

    def __init__(
        self, config: GlobalCoverageConfig, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._config = copy.deepcopy(config)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_scenario_tab(), "场景与覆盖")
        self.tabs.addTab(self._build_satellite_tab(), "卫星与链路")
        self.tabs.addTab(self._build_station_tab(), "地面站配置")

        self.run_button = QPushButton("开始仿真")
        self.run_button.setObjectName("primaryButton")
        self.run_button.clicked.connect(lambda: self._request_run(False))
        self.run_all_button = QPushButton("运行文档全部方案")
        self.run_all_button.clicked.connect(lambda: self._request_run(True))
        self.status_label = QLabel("就绪")
        self.status_label.setObjectName("statusLabel")

        actions = QHBoxLayout()
        actions.addWidget(self.run_button)
        actions.addWidget(self.run_all_button)
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
        splitter.setSizes([320, 560])

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

        self.resolution_field = _double_spin(0.1, 10.0, 0.1, 3)
        self.min_elevation_field = _double_spin(0.0, 90.0, 1.0, 2)
        coverage_form = QFormLayout()
        coverage_form.addRow("网格分辨率 / °", self.resolution_field)
        coverage_form.addRow("网格最低仰角 / °", self.min_elevation_field)
        coverage_group = QGroupBox("全球覆盖")
        coverage_group.setLayout(coverage_form)

        layout = QHBoxLayout(tab)
        layout.addWidget(scenario_group, 1)
        layout.addWidget(coverage_group, 1)
        return tab

    def _build_satellite_tab(self) -> QWidget:
        tab = QWidget()
        self.satellite_field = QComboBox()
        for label, value in SATELLITE_MODES:
            self.satellite_field.addItem(label, value)
        self.satellite_field.currentIndexChanged.connect(
            self._update_satellite_summary
        )
        self.satellite_summary = QLabel()
        self.satellite_summary.setObjectName("hintLabel")
        self.satellite_name_field = QLineEdit()
        self.satellite_name_field.textChanged.connect(
            self._update_satellite_summary
        )
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
        satellite_form.addRow("卫星方案", self.satellite_field)
        satellite_form.addRow("当前卫星", self.satellite_summary)
        satellite_form.addRow("参考星名称", self.satellite_name_field)
        satellite_form.addRow("参考星 SSC", self.ssc_field)
        satellite_form.addRow("传播步长 / s", self.satellite_step_field)
        satellite_form.addRow("参考星 TLE", tle_host)
        satellite_group = QGroupBox("轨道与三星偏置")
        satellite_group.setLayout(satellite_form)

        self.avoidance_enabled_field = QCheckBox("启用视线太阳干扰规避")
        self.avoidance_angle_field = _double_spin(0.0, 180.0, 1.0, 2)
        self.avoidance_enabled_field.toggled.connect(
            self.avoidance_angle_field.setEnabled
        )
        avoidance_form = QFormLayout()
        avoidance_form.addRow(self.avoidance_enabled_field)
        avoidance_form.addRow("规避角度 / °", self.avoidance_angle_field)
        avoidance_group = QGroupBox("干扰规避")
        avoidance_group.setLayout(avoidance_form)

        note = QLabel(
            "三星由参考星 TLE 生成：RAAN 偏移 0°/45°/90°，"
            "平近点角偏移 0°/−90°/−180°；星间链路按几何可见计算。"
        )
        note.setWordWrap(True)
        note.setObjectName("hintLabel")
        right = QVBoxLayout()
        right.addWidget(avoidance_group)
        right.addWidget(note)
        right.addStretch(1)

        layout = QHBoxLayout(tab)
        layout.addWidget(satellite_group, 2)
        layout.addLayout(right, 1)
        return tab

    def _build_station_tab(self) -> QWidget:
        tab = QWidget()
        self.station_preset_field = QComboBox()
        for label, value in STATION_PRESETS:
            self.station_preset_field.addItem(label, value)
        load_button = QPushButton("载入预设")
        load_button.clicked.connect(self._load_station_preset)
        add_button = QPushButton("添加地面站")
        add_button.clicked.connect(self._add_station)
        edit_button = QPushButton("编辑选中")
        edit_button.clicked.connect(self._edit_selected_station)
        delete_button = QPushButton("删除选中")
        delete_button.clicked.connect(self._delete_selected_stations)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("文档预设"))
        toolbar.addWidget(self.station_preset_field)
        toolbar.addWidget(load_button)
        toolbar.addSpacing(16)
        toolbar.addWidget(add_button)
        toolbar.addWidget(edit_button)
        toolbar.addWidget(delete_button)
        toolbar.addStretch(1)

        self.station_table = QTableWidget(0, 5)
        self.station_table.setHorizontalHeaderLabels(
            ("地面站", "纬度 / °", "经度 / °", "高度 / km", "最低仰角 / °")
        )
        self.station_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.station_table.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.station_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.station_table.verticalHeader().setVisible(False)
        header = self.station_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, 5):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.station_table.cellDoubleClicked.connect(
            lambda _row, _column: self._edit_selected_station()
        )

        hint = QLabel("表格中的每个地面站都会参与仿真；双击一行可编辑参数。")
        hint.setObjectName("hintLabel")
        layout = QVBoxLayout(tab)
        layout.addLayout(toolbar)
        layout.addWidget(self.station_table, 1)
        layout.addWidget(hint)
        return tab

    def read_config(self) -> GlobalCoverageConfig:
        config = copy.deepcopy(self._config)
        config.scenario.name = self.scenario_field.text().strip()
        config.scenario.start_time = self.start_field.text().strip()
        config.scenario.stop_time = self.stop_field.text().strip()
        config.satellite_group.mode = str(self.satellite_field.currentData())
        config.satellite.name = self.satellite_name_field.text().strip()
        config.satellite.ssc = self.ssc_field.value()
        config.satellite.step = self.satellite_step_field.value()
        config.satellite.tle_file = Path(self.tle_field.text().strip())
        config.coverage.resolution = self.resolution_field.value()
        config.coverage.min_elevation = self.min_elevation_field.value()
        config.interference.enabled = self.avoidance_enabled_field.isChecked()
        config.interference.angle = self.avoidance_angle_field.value()
        config.stations = self._read_stations()
        if not config.scenario.name or not config.satellite.name:
            raise ValueError("场景名称和参考星名称不能为空。")
        if not config.satellite.tle_file.is_file():
            raise ValueError(f"TLE 文件不存在：{config.satellite.tle_file}")
        return config

    def write_config(self, config: GlobalCoverageConfig) -> None:
        self._config = copy.deepcopy(config)
        self.scenario_field.setText(config.scenario.name)
        self.start_field.setText(config.scenario.start_time)
        self.stop_field.setText(config.scenario.stop_time)
        self.resolution_field.setValue(config.coverage.resolution)
        self.min_elevation_field.setValue(config.coverage.min_elevation)
        self.satellite_name_field.setText(config.satellite.name)
        self.ssc_field.setValue(config.satellite.ssc)
        self.satellite_step_field.setValue(config.satellite.step)
        self.tle_field.setText(str(config.satellite.tle_file))
        self.avoidance_enabled_field.setChecked(config.interference.enabled)
        self.avoidance_angle_field.setValue(config.interference.angle)
        self.avoidance_angle_field.setEnabled(config.interference.enabled)
        self._select_data(self.satellite_field, config.satellite_group.mode)
        preset = "all" if len(config.stations) >= 5 else "domestic"
        if len(config.stations) == 1:
            preset = "single"
        self._select_data(self.station_preset_field, preset)
        self._fill_station_table(config.stations)
        self._update_satellite_summary()

    def set_busy(self, busy: bool) -> None:
        self.run_button.setEnabled(not busy)
        self.run_all_button.setEnabled(not busy)
        self.tabs.setEnabled(not busy)
        self.plot_widget.set_busy(busy)

    def set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def show_result(self, result, document_scenarios: bool = False) -> None:
        from stk_simulation.simulations.global_coverage.service import (
            render_global_coverage,
        )

        self.plot_widget.show_result(result, render_global_coverage)
        self.set_status(
            f"文档全部方案完成 · {result.output.result_dir}"
            if document_scenarios
            else f"完成 · {result.output.image_path}"
        )

    def _request_run(self, document_scenarios: bool) -> None:
        try:
            config = self.read_config()
        except Exception as error:
            QMessageBox.critical(self, "参数错误", str(error))
            return
        self.set_status(
            "准备运行文档全部方案..."
            if document_scenarios
            else "准备连接 STK..."
        )
        self.run_requested.emit(config, document_scenarios)

    def _browse_tle(self) -> None:
        current = Path(self.tle_field.text())
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "选择参考卫星 TLE",
            str(current.parent),
            "TLE 文件 (*.txt *.tle);;全部文件 (*.*)",
        )
        if selected:
            self.tle_field.setText(selected)

    def _load_station_preset(self) -> None:
        self._fill_station_table(
            station_template(str(self.station_preset_field.currentData()))
        )

    def _add_station(self) -> None:
        existing_names = {
            self._station_from_row(row).name.casefold()
            for row in range(self.station_table.rowCount())
        }
        number = 1
        while f"station{number}" in existing_names:
            number += 1
        station = StationConfig(f"Station{number}", 0.0, 0.0, 0.0, 15.0)
        created = StationDialog.show(self, "添加地面站", station)
        if created is None:
            return
        if created.name.casefold() in existing_names:
            QMessageBox.critical(self, "参数错误", "地面站名称不能重复。")
            return
        row = self._insert_station(created)
        self.station_table.selectRow(row)

    def _edit_selected_station(self) -> None:
        selected_rows = sorted(
            {index.row() for index in self.station_table.selectedIndexes()}
        )
        if len(selected_rows) != 1:
            QMessageBox.information(self, "编辑地面站", "请先选择一个地面站。")
            return
        row = selected_rows[0]
        updated = StationDialog.show(
            self, "编辑地面站", self._station_from_row(row)
        )
        if updated is None:
            return
        other_names = {
            self._station_from_row(other).name.casefold()
            for other in range(self.station_table.rowCount())
            if other != row
        }
        if updated.name.casefold() in other_names:
            QMessageBox.critical(self, "参数错误", "地面站名称不能重复。")
            return
        self._write_station_row(row, updated)

    def _delete_selected_stations(self) -> None:
        selected_rows = sorted(
            {index.row() for index in self.station_table.selectedIndexes()},
            reverse=True,
        )
        if not selected_rows:
            QMessageBox.information(self, "删除地面站", "请先选择要删除的地面站。")
            return
        for row in selected_rows:
            self.station_table.removeRow(row)

    def _update_satellite_summary(self) -> None:
        names = [self.satellite_name_field.text().strip() or "TN01A"]
        if self.satellite_field.currentData() == "multi":
            names.extend(("TN02A", "TN03A"))
        self.satellite_summary.setText("、".join(names))

    def _fill_station_table(self, stations: list[StationConfig]) -> None:
        self.station_table.setRowCount(0)
        for station in stations:
            self._insert_station(station)

    def _insert_station(self, station: StationConfig) -> int:
        row = self.station_table.rowCount()
        self.station_table.insertRow(row)
        self._write_station_row(row, station)
        return row

    def _write_station_row(self, row: int, station: StationConfig) -> None:
        values = (
            station.name,
            f"{station.lat:.8g}",
            f"{station.lon:.8g}",
            f"{station.alt:g}",
            f"{station.min_elevation:g}",
        )
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.station_table.setItem(row, column, item)

    def _station_from_row(self, row: int) -> StationConfig:
        values = [self.station_table.item(row, column).text() for column in range(5)]
        return StationConfig(
            name=values[0].strip(),
            lat=float(values[1]),
            lon=float(values[2]),
            alt=float(values[3]),
            min_elevation=float(values[4]),
        )

    def _read_stations(self) -> list[StationConfig]:
        stations = [
            self._station_from_row(row)
            for row in range(self.station_table.rowCount())
        ]
        if not stations:
            raise ValueError("请至少添加一个地面站。")
        names = [station.name.casefold() for station in stations]
        if len(names) != len(set(names)):
            raise ValueError("地面站名称不能重复。")
        return stations

    @staticmethod
    def _select_data(combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        combo.setCurrentIndex(max(index, 0))


def _double_spin(
    minimum: float, maximum: float, step: float, decimals: int
) -> QDoubleSpinBox:
    field = QDoubleSpinBox()
    field.setRange(minimum, maximum)
    field.setSingleStep(step)
    field.setDecimals(decimals)
    return field
