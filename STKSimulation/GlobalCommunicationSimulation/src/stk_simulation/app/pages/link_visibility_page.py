"""星地建链与 AER 预报桌面端功能页（支持单站/双站中继、双引擎对比、CSV 导出）。"""

from __future__ import annotations

import copy
import csv
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
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
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from stk_simulation.app.widgets.plot_widget import PlotWidget
from stk_simulation.simulations.link_visibility.config import (
    LinkVisibilityConfig,
    LinkVisibilityResult,
)
from stk_simulation.simulations.link_visibility.plot import (
    plot_elevation_curve,
    plot_ground_track_2d,
    plot_skyplot_polar,
)


class LinkVisibilityPage(QWidget):
    run_requested = Signal(object, str)  # (LinkVisibilityConfig, run_mode)

    def __init__(self, default_config: LinkVisibilityConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = copy.deepcopy(default_config)
        self._last_result: LinkVisibilityResult | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        root_layout = QHBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        root_layout.addWidget(splitter)

        # 左侧参数配置栏
        left = QWidget()
        left_layout = QVBoxLayout(left)

        sat_box = QGroupBox("卫星与时间窗口配置")
        sat_form = QFormLayout(sat_box)
        self.sat_name_edit = QLineEdit(self._config.satellite.name)
        self.ssc_edit = QLineEdit(str(self._config.satellite.ssc))
        self.start_edit = QLineEdit(self._config.scenario.start_time)
        self.stop_edit = QLineEdit(self._config.scenario.stop_time)
        sat_form.addRow("卫星名称", self.sat_name_edit)
        sat_form.addRow("NORAD SSC", self.ssc_edit)
        sat_form.addRow("开始时间 (UTCG)", self.start_edit)
        sat_form.addRow("结束时间 (UTCG)", self.stop_edit)
        left_layout.addWidget(sat_box)

        st_box = QGroupBox("地面站与空间约束 (GSO 干扰规避)")
        st_form = QFormLayout(st_box)
        st0 = self._config.stations[0]
        self.st_name_edit = QLineEdit(st0.name)
        self.lat_spin = QDoubleSpinBox()
        self.lat_spin.setRange(-90.0, 90.0)
        self.lat_spin.setDecimals(4)
        self.lat_spin.setValue(st0.latitude_deg)
        self.lon_spin = QDoubleSpinBox()
        self.lon_spin.setRange(-180.0, 180.0)
        self.lon_spin.setDecimals(4)
        self.lon_spin.setValue(st0.longitude_deg)
        self.min_el_spin = QDoubleSpinBox()
        self.min_el_spin.setRange(0.0, 85.0)
        self.min_el_spin.setValue(st0.min_elevation_deg)
        self.gso_spin = QDoubleSpinBox()
        self.gso_spin.setRange(0.0, 45.0)
        self.gso_spin.setValue(st0.gso_avoid_deg)
        self.dual_check = QCheckBox("启用两地协同中继模式 (上海临港 ⇄ 喀什站同时可见)")

        st_form.addRow("主站名称", self.st_name_edit)
        st_form.addRow("纬度 (°)", self.lat_spin)
        st_form.addRow("经度 (°)", self.lon_spin)
        st_form.addRow("最低仰角 (°)", self.min_el_spin)
        st_form.addRow("GSO 隔离角 (°)", self.gso_spin)
        st_form.addRow("", self.dual_check)
        left_layout.addWidget(st_box)

        btn_row = QHBoxLayout()
        self.run_btn = QPushButton("开始建链预报计算")
        self.run_btn.setObjectName("primaryButton")
        self.run_btn.clicked.connect(lambda: self._emit_run("normal"))
        self.compare_btn = QPushButton("⚖️ 双引擎交叉比对 (STK vs Python)")
        self.compare_btn.clicked.connect(lambda: self._emit_run("compare"))
        self.export_btn = QPushButton("导出 AER CSV")
        self.export_btn.setEnabled(False)
        self.export_btn.clicked.connect(self._export_csv)
        btn_row.addWidget(self.run_btn)
        btn_row.addWidget(self.compare_btn)
        btn_row.addWidget(self.export_btn)
        left_layout.addLayout(btn_row)

        self.status_label = QLabel("就绪：等待启动建链计算")
        left_layout.addWidget(self.status_label)

        # 过境窗口表
        self.win_table = QTableWidget(0, 5)
        self.win_table.setHorizontalHeaderLabels(["圈次", "开始时间 (北京时间)", "结束时间 (北京时间)", "持续(秒)", "最高仰角(°)"])
        self.win_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        left_layout.addWidget(self.win_table, 1)

        # 右侧多视图画布与对比表
        right_tabs = QTabWidget()
        self.el_plot = PlotWidget()
        self.sky_plot = PlotWidget()
        self.track_plot = PlotWidget()
        self.diff_table = QTableWidget(0, 6)
        self.diff_table.setHorizontalHeaderLabels([
            "圈次", "STK 开始", "Python 开始", "入境误差(秒)", "出境误差(秒)", "最高仰角差(°)"
        ])
        self.diff_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        right_tabs.addTab(self.el_plot, "📈 仰角-时间曲线")
        right_tabs.addTab(self.sky_plot, "🧭 极坐标天空图 (Skyplot)")
        right_tabs.addTab(self.track_plot, "🗺️ 星下点轨迹与建链弧段")
        right_tabs.addTab(self.diff_table, "⚖️ STK vs Python 精度比对表")
        self.right_tabs = right_tabs

        splitter.addWidget(left)
        splitter.addWidget(right_tabs)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)

    def _emit_run(self, mode: str) -> None:
        cfg = copy.deepcopy(self._config)
        cfg.satellite.name = self.sat_name_edit.text().strip() or "SAT"
        cfg.satellite.ssc = int(self.ssc_edit.text().strip() or "59705")
        cfg.scenario.start_time = self.start_edit.text().strip()
        cfg.scenario.stop_time = self.stop_edit.text().strip()
        cfg.stations[0].name = self.st_name_edit.text().strip() or "主站"
        cfg.stations[0].latitude_deg = float(self.lat_spin.value())
        cfg.stations[0].longitude_deg = float(self.lon_spin.value())
        cfg.stations[0].min_elevation_deg = float(self.min_el_spin.value())
        cfg.stations[0].gso_avoid_deg = float(self.gso_spin.value())
        cfg.dual_station_sync = self.dual_check.isChecked()
        self.run_requested.emit(cfg, mode)

    def set_busy(self, busy: bool) -> None:
        self.run_btn.setEnabled(not busy)
        self.compare_btn.setEnabled(not busy)

    def set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def show_result(self, result: LinkVisibilityResult) -> None:
        self._last_result = result
        self.export_btn.setEnabled(len(result.aer_records) > 0)
        self.status_label.setText(
            f"计算完成 [{result.engine_used.upper()}]：共 {len(result.windows)} 个可见窗口，"
            f"累计可用时长 {result.total_duration_sec:.1f} 秒"
        )

        self.win_table.setRowCount(len(result.windows))
        for r_idx, w in enumerate(result.windows):
            vals = [
                str(w.access_number),
                w.start_time,
                w.stop_time,
                f"{w.duration_sec:.1f}",
                f"{w.max_elevation_deg:.2f}",
            ]
            for c_idx, val in enumerate(vals):
                self.win_table.setItem(r_idx, c_idx, QTableWidgetItem(val))

        plot_elevation_curve(result, self.el_plot.figure)
        self.el_plot.canvas.draw_idle()
        plot_skyplot_polar(result, self.sky_plot.figure)
        self.sky_plot.canvas.draw_idle()
        plot_ground_track_2d(result, self.track_plot.figure)
        self.track_plot.canvas.draw_idle()

        if result.diff_items:
            self.diff_table.setRowCount(len(result.diff_items))
            for r_idx, d in enumerate(result.diff_items):
                vals = [
                    str(d.access_number),
                    d.stk_start,
                    d.py_start,
                    f"{d.start_diff_sec:+.2f}s",
                    f"{d.stop_diff_sec:+.2f}s",
                    f"{d.max_el_diff_deg:+.3f}°",
                ]
                for c_idx, val in enumerate(vals):
                    self.diff_table.setItem(r_idx, c_idx, QTableWidgetItem(val))
            self.right_tabs.setCurrentWidget(self.diff_table)

    def _export_csv(self) -> None:
        if not self._last_result or not self._last_result.aer_records:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 AER CSV", "aer_export.csv", "CSV Files (*.csv)"
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["圈次", "地面站", "时间(北京时间)", "方位角(°)", "仰角(°)", "距离(km)"])
            for r in self._last_result.aer_records:
                writer.writerow([r.access_number, r.station_name, r.time, f"{r.azimuth_deg:.2f}", f"{r.elevation_deg:.2f}", f"{r.range_km:.2f}"])
        QMessageBox.information(self, "导出成功", f"AER 数据已保存至：\n{path}")
