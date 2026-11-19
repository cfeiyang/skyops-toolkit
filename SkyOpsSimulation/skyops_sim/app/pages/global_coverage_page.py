"""全球通信时长功能页。"""

from __future__ import annotations

import copy

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSizePolicy,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from skyops_sim.app.dialogs.station_dialog import StationDialog
from skyops_sim.app.icons import action_button
from skyops_sim.app.widgets.plot_widget import PlotWidget
from skyops_sim.app.widgets.side_navigation import SectionStack, SideNavigation
from skyops_sim.simulations.common import SatelliteConfig
from skyops_sim.simulations.global_coverage.config import GlobalCoverageConfig
from skyops_sim.simulations.global_coverage.presets import StationConfig


SATELLITE_MODES = (("单星", "single"), ("三星几何星间中继", "multi"))


class GlobalCoveragePage(QWidget):
    run_requested = Signal(object, str)

    def __init__(
        self, config: GlobalCoverageConfig, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._config = copy.deepcopy(config)

        self.sections = SectionStack()
        self.parameter_pages = (
            self._build_scenario_tab(), self._build_satellite_tab(), self._build_station_tab(),
        )
        for page in self.parameter_pages:
            self.sections.addWidget(page)

        self.run_button = action_button("开始仿真", "play", primary=True)
        self.run_button.clicked.connect(lambda: self._request_run("normal"))
        self.gain_button = action_button("计算选中站增益", "chart-no-axes-column-increasing")
        self.gain_button.clicked.connect(self._request_gain)
        self.run_all_button = action_button("运行文档全部方案", "layers")
        self.run_all_button.clicked.connect(lambda: self._request_run("document"))
        self.status_label = QLabel("就绪")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.status_label.setMinimumWidth(155)

        actions = QHBoxLayout()
        actions.addWidget(self.status_label, 1)
        actions.addWidget(self.run_all_button)
        actions.addWidget(self.gain_button)
        actions.addWidget(self.run_button)

        self.result_tabs = QTabWidget()
        self.result_tabs.setDocumentMode(True)
        self._plot_widgets: list[PlotWidget] = []
        self._replace_result_tabs((("仿真结果", None),))
        self.gain_summary_label = QLabel()
        self.gain_summary_label.setObjectName("gainSummary")
        self.gain_summary_label.setVisible(False)
        result_panel = QWidget()
        result_layout = QVBoxLayout(result_panel)
        result_layout.setContentsMargins(0, 0, 0, 0)
        result_layout.addWidget(self.gain_summary_label)
        result_layout.addWidget(self.result_tabs, 1)
        self.sections.addWidget(result_panel)
        self.sections.currentChanged.connect(self._show_section_actions)

        panel = QFrame()
        panel.setObjectName("toolPanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(13, 10, 13, 11)
        panel_layout.addWidget(self.sections, 1)
        panel_layout.addLayout(actions)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        layout.addWidget(SideNavigation((
            ("场景与覆盖", "globe"), ("星座与约束", "satellite"),
            ("地面站", "radio-tower"), ("仿真结果", "chart-no-axes-column-increasing"),
        ), self.sections))
        self.panel_area = QVBoxLayout()
        self.panel_area.addWidget(panel)
        self.panel_area.addStretch(1)
        layout.addLayout(self.panel_area, 1)
        self.write_config(config)
        self._show_section_actions(0)

    def _show_section_actions(self, index: int) -> None:
        self.gain_button.setVisible(index == 2)
        expanded = index in (2, 3)
        self.panel_area.setStretch(0, int(expanded))
        self.panel_area.setStretch(1, int(not expanded))

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

        self.resolution_field = _double_spin(0.1, 10.0, 0.1, 3, " °")
        self.min_elevation_field = _double_spin(0.0, 90.0, 1.0, 2, " °")
        coverage_form = QFormLayout()
        coverage_form.addRow("网格分辨率", self.resolution_field)
        coverage_form.addRow("网格最低仰角", self.min_elevation_field)
        coverage_group = QGroupBox("全球覆盖")
        coverage_group.setLayout(coverage_form)

        layout = QHBoxLayout(tab)
        layout.addWidget(scenario_group, 1, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(coverage_group, 1, Qt.AlignmentFlag.AlignTop)
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
        self.satellite_step_field = _double_spin(
            1.0, 86400.0, 1.0, 2, " s"
        )

        satellite_form = QFormLayout()
        satellite_form.addRow("卫星方案", self.satellite_field)
        satellite_form.addRow("当前卫星", self.satellite_summary)
        satellite_form.addRow("传播步长", self.satellite_step_field)
        satellite_group = QGroupBox("轨道与三星偏置")
        satellite_group.setLayout(satellite_form)

        self.avoidance_enabled_field = QCheckBox("启用视线太阳干扰规避")
        self.avoidance_angle_field = _double_spin(
            0.0, 180.0, 1.0, 2, " °"
        )
        self.avoidance_enabled_field.toggled.connect(
            self.avoidance_angle_field.setEnabled
        )
        avoidance_form = QFormLayout()
        avoidance_form.addRow(self.avoidance_enabled_field)
        avoidance_form.addRow("规避角度", self.avoidance_angle_field)
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
        layout.addWidget(satellite_group, 2, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(right, 1)
        return tab

    def _build_station_tab(self) -> QWidget:
        tab = QWidget()
        add_button = action_button("添加地面站", "plus")
        add_button.clicked.connect(self._add_station)
        edit_button = action_button("编辑选中", "pencil")
        edit_button.clicked.connect(self._edit_selected_station)
        delete_button = action_button("删除选中", "trash-2")
        delete_button.clicked.connect(self._delete_selected_stations)

        toolbar = QHBoxLayout()
        toolbar.addWidget(add_button)
        toolbar.addWidget(edit_button)
        toolbar.addWidget(delete_button)
        toolbar.addStretch(1)

        self.station_table = QTableWidget(0, 5)
        self.station_table.setAlternatingRowColors(True)
        self.station_table.setShowGrid(False)
        self.station_table.setHorizontalHeaderLabels(
            ("地面站", "纬度 / °", "经度 / °", "海拔 / m", "最低仰角 / °")
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

        hint = QLabel(
            "表格中的每个地面站都会参与仿真；选中一行后可计算该站带来的覆盖增益。"
        )
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
        config.satellite.step = self.satellite_step_field.value()
        config.coverage.resolution = self.resolution_field.value()
        config.coverage.min_elevation = self.min_elevation_field.value()
        config.interference.enabled = self.avoidance_enabled_field.isChecked()
        config.interference.angle = self.avoidance_angle_field.value()
        config.stations = self._read_stations()
        if not config.scenario.name:
            raise ValueError("场景名称不能为空。")
        if config.satellite_group.mode == "multi" and config.satellite.name.upper() in {"TN02A", "TN03A"}:
            raise ValueError("参考星名称不能与三星方案中的派生星重名。")
        return config

    def write_config(self, config: GlobalCoverageConfig) -> None:
        self._config = copy.deepcopy(config)
        self.scenario_field.setText(config.scenario.name)
        self.start_field.setText(config.scenario.start_time)
        self.stop_field.setText(config.scenario.stop_time)
        self.resolution_field.setValue(config.coverage.resolution)
        self.min_elevation_field.setValue(config.coverage.min_elevation)
        self.satellite_step_field.setValue(config.satellite.step)
        self.avoidance_enabled_field.setChecked(config.interference.enabled)
        self.avoidance_angle_field.setValue(config.interference.angle)
        self.avoidance_angle_field.setEnabled(config.interference.enabled)
        self._select_data(self.satellite_field, config.satellite_group.mode)
        self._fill_station_table(config.stations)
        self._update_satellite_summary()

    def set_reference_satellite(self, profile) -> None:
        self._config.satellite = SatelliteConfig.from_reference(profile, self.satellite_step_field.value())
        self._update_satellite_summary()

    def set_busy(self, busy: bool) -> None:
        self.run_button.setEnabled(not busy)
        self.gain_button.setEnabled(not busy)
        self.run_all_button.setEnabled(not busy)
        for page in self.parameter_pages:
            page.setEnabled(not busy)
        for plot_widget in self._plot_widgets:
            plot_widget.set_busy(busy)

    def set_status(self, text: str) -> None:
        self.status_label.setText(text)
        self.status_label.setToolTip(text)

    def show_result(self, result, run_mode: str = "normal") -> None:
        from skyops_sim.simulations.global_coverage.service import (
            render_global_coverage,
        )

        views = result.comparison_results or (("仿真结果", result),)
        self._replace_result_tabs(
            views,
            render_global_coverage,
            current_index=2 if run_mode == "gain" else 0,
        )
        self.sections.setCurrentIndex(3)
        if run_mode == "document":
            self.gain_summary_label.setVisible(False)
            self.set_status(f"文档全部方案完成 · {result.output.result_dir}")
        elif run_mode == "gain":
            gain = result.gain_summary
            if gain is None:
                raise RuntimeError("增益结果缺少统计摘要。")
            self.gain_summary_label.setText(
                f"新增站：{gain.station_name}　"
                f"最大时长增益：{gain.max_hour:.3f} h　"
                f"受益区域平均增益：{gain.mean_positive_hour:.3f} h　"
                f"新增覆盖：{gain.new_coverage_percent:.3f}% "
                f"（约 {gain.new_coverage_area_km2:,.0f} km²）"
            )
            self.gain_summary_label.setVisible(True)
            self.set_status(
                f"{gain.station_name} 增益完成 · 最大增加 {gain.max_hour:.3f} h"
            )
        else:
            self.gain_summary_label.setVisible(False)
            self.set_status(f"完成 · {result.output.image_path}")

    def _request_run(self, run_mode: str) -> None:
        try:
            config = self.read_config()
        except Exception as error:
            QMessageBox.critical(self, "参数错误", str(error))
            return
        self._submit(config, run_mode)

    def _request_gain(self) -> None:
        selected_rows = sorted(
            {index.row() for index in self.station_table.selectedIndexes()}
        )
        if len(selected_rows) != 1:
            QMessageBox.information(
                self, "计算地面站增益", "请先在地面站表格中选择一个新增站。"
            )
            return
        try:
            config = self.read_config()
        except Exception as error:
            QMessageBox.critical(self, "参数错误", str(error))
            return
        config.comparison_station_name = config.stations[selected_rows[0]].name
        self._submit(config, "gain")

    def _submit(self, config: GlobalCoverageConfig, run_mode: str) -> None:
        status = {
            "normal": "正在准备仿真…",
            "gain": f"准备计算 {config.comparison_station_name} 的覆盖增益...",
            "document": "准备运行文档全部方案...",
        }
        self.set_status(status[run_mode])
        self.run_requested.emit(config, run_mode)

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
        names = [self._config.satellite.name]
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
            f"{station.alt * 1000.0:g}",
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
            alt=float(values[3]) / 1000.0,
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

    def _replace_result_tabs(
        self, views, renderer=None, current_index: int = 0
    ) -> None:
        while self.result_tabs.count():
            widget = self.result_tabs.widget(0)
            self.result_tabs.removeTab(0)
            widget.deleteLater()
        self._plot_widgets.clear()
        for label, result in views:
            plot_widget = PlotWidget()
            if result is not None and renderer is not None:
                plot_widget.show_result(result, renderer)
            self._plot_widgets.append(plot_widget)
            self.result_tabs.addTab(plot_widget, label)
        self.result_tabs.setCurrentIndex(
            min(max(current_index, 0), self.result_tabs.count() - 1)
        )
        self.result_tabs.tabBar().setVisible(self.result_tabs.count() > 1)


def _double_spin(
    minimum: float,
    maximum: float,
    step: float,
    decimals: int,
    suffix: str = "",
) -> QDoubleSpinBox:
    field = QDoubleSpinBox()
    field.setRange(minimum, maximum)
    field.setSingleStep(step)
    field.setDecimals(decimals)
    field.setSuffix(suffix)
    return field
