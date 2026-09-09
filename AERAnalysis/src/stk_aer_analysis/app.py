"""STK 地面站可见性与 AER 分析桌面界面。"""

from __future__ import annotations

import sys
from collections import defaultdict
from datetime import datetime

import matplotlib.dates as mdates
from matplotlib import rcParams
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtCore import QDateTime, QTime, Qt
from PySide6.QtGui import QCloseEvent, QFont, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from stk_aer_analysis.controller import ScenarioController
from stk_aer_analysis.models import ScenarioRequest, StationConfig
from stk_aer_analysis.paths import package_resource


TLE_URL = "https://celestrak.org/NORAD/elements/gp.php?CATNR={ssc}&FORMAT=TLE"
APP_ICON = package_resource("assets", "app_icon.ico")

rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
rcParams["axes.unicode_minus"] = False

STYLE_SHEET = """
QWidget {
    color: #1f2937;
    font-size: 14px;
}
QMainWindow, QWidget {
    background: #f5f7fa;
}
QGroupBox {
    background: white;
    border: 1px solid #dce2ea;
    border-radius: 7px;
    margin-top: 12px;
    padding-top: 12px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateTimeEdit,
QPlainTextEdit, QTableWidget {
    background: white;
    border: 1px solid #cbd5e1;
    border-radius: 4px;
    min-height: 30px;
}
QTabWidget::pane {
    background: white;
    border: 1px solid #dce2ea;
}
QTabBar::tab {
    background: #e8edf3;
    border: 1px solid #d1d9e3;
    padding: 8px 18px;
}
QTabBar::tab:selected {
    background: white;
    color: #1769aa;
    font-weight: 600;
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
    min-height: 38px;
}
#primaryButton:hover {
    background: #125b94;
}
#titleLabel {
    color: #163a63;
    font-size: 22px;
    font-weight: 600;
}
#statusLabel {
    color: #526273;
}
"""


class StationDialog(QDialog):
    def __init__(
        self,
        parent: QWidget,
        title: str,
        station: StationConfig,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(390)
        self.station: StationConfig | None = None

        self.name_field = QLineEdit(station.name)
        self.latitude_field = _number_field(
            station.latitude_deg, -90.0, 90.0, 6, 0.0001, " °"
        )
        self.longitude_field = _number_field(
            station.longitude_deg, -180.0, 180.0, 6, 0.0001, " °"
        )
        self.altitude_field = _number_field(
            station.altitude_m, -1000.0, 100000.0, 2, 1.0, " m"
        )
        self.elevation_field = _number_field(
            station.min_elevation_deg, 0.0, 90.0, 2, 1.0, " °"
        )

        form = QFormLayout()
        form.addRow("地面站名称", self.name_field)
        form.addRow("纬度（北正南负）", self.latitude_field)
        form.addRow("经度（东正西负）", self.longitude_field)
        form.addRow("海拔高度", self.altitude_field)
        form.addRow("最低仰角", self.elevation_field)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _accept(self) -> None:
        name = self.name_field.text().strip()
        if not name:
            QMessageBox.warning(self, "参数错误", "地面站名称不能为空。")
            return
        self.station = StationConfig(
            name=name,
            latitude_deg=self.latitude_field.value(),
            longitude_deg=self.longitude_field.value(),
            altitude_m=self.altitude_field.value(),
            min_elevation_deg=self.elevation_field.value(),
        )
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("STK 可见性与 AER 分析")
        self.setWindowIcon(QIcon(str(APP_ICON)))
        self.resize(1220, 820)
        self.setMinimumSize(1000, 680)

        self.controller = ScenarioController(self)
        self.controller.busy_changed.connect(self._set_busy)
        self.controller.progress.connect(self._append_log)
        self.controller.completed.connect(self._show_result)
        self.controller.failed.connect(self._show_error)

        title = QLabel("STK 可见性与 AER 分析")
        title.setObjectName("titleLabel")
        subtitle = QLabel(
            "按指定时间计算成都地面站对 01A 卫星的可见时段、方位角和仰角"
        )
        subtitle.setObjectName("statusLabel")

        self.settings_widget = self._build_settings()
        stations_widget = self._build_stations()
        config_splitter = QSplitter(Qt.Orientation.Horizontal)
        config_splitter.addWidget(self.settings_widget)
        config_splitter.addWidget(stations_widget)
        config_splitter.setSizes([450, 730])

        self.access_table = _result_table(
            ("序号", "可见开始时间 / UTC", "可见结束时间 / UTC", "时长 / s"),
            stretch_column=2,
        )
        self.aer_table = _result_table(
            ("时段", "采样时间 / UTC", "方位角 / °", "仰角 / °", "距离 / km"),
            stretch_column=1,
        )
        self.figure = Figure(figsize=(9, 6), facecolor="white")
        self.canvas = FigureCanvasQTAgg(self.figure)
        self._draw_plot_placeholder("运行仿真后将在这里显示方位角和仰角曲线")

        self.tabs = QTabWidget()
        self.tabs.addTab(config_splitter, "场景配置")
        self.tabs.addTab(self.access_table, "可见时间段")
        self.tabs.addTab(self.aer_table, "AER 数据")
        self.tabs.addTab(self.canvas, "方位角 / 仰角曲线")

        self.status_label = QLabel("等待仿真")
        self.status_label.setObjectName("statusLabel")
        self.run_button = QPushButton("创建场景并计算可见性")
        self.run_button.setObjectName("primaryButton")
        self.run_button.clicked.connect(self._start)

        action_layout = QHBoxLayout()
        action_layout.addWidget(self.status_label)
        action_layout.addStretch(1)
        action_layout.addWidget(self.run_button)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self.tabs, 1)
        layout.addLayout(action_layout)
        self.setCentralWidget(central)

    def _build_settings(self) -> QWidget:
        self.stk_mode = QComboBox()
        self.stk_mode.addItem("新建 STK 12 实例", "new")
        self.stk_mode.addItem("连接正在运行的 STK 12", "running")

        connection_group = QGroupBox("STK 连接")
        connection_form = QFormLayout(connection_group)
        connection_form.addRow("连接方式", self.stk_mode)

        now = QDateTime.currentDateTime()
        start = QDateTime(now.date(), QTime(0, 0, 0))
        stop = start.addDays(1)
        self.scenario_name = QLineEdit("AERAnalysis")
        self.start_time = _date_time_field(start)
        self.stop_time = _date_time_field(stop)

        scenario_group = QGroupBox("场景参数")
        scenario_form = QFormLayout(scenario_group)
        scenario_form.addRow("场景名称", self.scenario_name)
        scenario_form.addRow("开始时间（电脑本地）", self.start_time)
        scenario_form.addRow("结束时间（电脑本地）", self.stop_time)

        self.satellite_name = QLineEdit("TN01A")
        self.satellite_ssc = QSpinBox()
        self.satellite_ssc.setRange(1, 999999)
        self.satellite_ssc.setValue(59705)
        self.propagation_step = _number_field(
            60.0, 1.0, 3600.0, 1, 10.0, " s"
        )
        self.tle_url = QLineEdit(TLE_URL.format(ssc=59705))
        self.satellite_ssc.valueChanged.connect(self._update_tle_url)

        satellite_group = QGroupBox("01A 卫星参数")
        satellite_form = QFormLayout(satellite_group)
        satellite_form.addRow("卫星名称", self.satellite_name)
        satellite_form.addRow("SSC 编号", self.satellite_ssc)
        satellite_form.addRow("传播步长", self.propagation_step)
        satellite_form.addRow("TLE 地址", self.tle_url)

        self.analysis_station = QComboBox()
        self.aer_step = _number_field(10.0, 1.0, 3600.0, 1, 5.0, " s")
        analysis_group = QGroupBox("可见性分析")
        analysis_form = QFormLayout(analysis_group)
        analysis_form.addRow("分析地面站", self.analysis_station)
        analysis_form.addRow("AER 采样间隔", self.aer_step)

        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 6, 0)
        layout.addWidget(connection_group)
        layout.addWidget(scenario_group)
        layout.addWidget(satellite_group)
        layout.addWidget(analysis_group)
        layout.addStretch(1)
        return panel

    def _build_stations(self) -> QWidget:
        self.station_table = QTableWidget(0, 5)
        self.station_table.setHorizontalHeaderLabels(
            ("地面站", "纬度 / °", "经度 / °", "海拔 / m", "最低仰角 / °")
        )
        self.station_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.station_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.station_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        header = self.station_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, 5):
            header.setSectionResizeMode(
                column, QHeaderView.ResizeMode.ResizeToContents
            )
        self.station_table.doubleClicked.connect(self._edit_station)

        self.add_button = QPushButton("添加地面站")
        self.edit_button = QPushButton("编辑选中站")
        self.delete_button = QPushButton("删除选中站")
        self.add_button.clicked.connect(self._add_station)
        self.edit_button.clicked.connect(self._edit_station)
        self.delete_button.clicked.connect(self._delete_station)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.add_button)
        button_layout.addWidget(self.edit_button)
        button_layout.addWidget(self.delete_button)
        button_layout.addStretch(1)

        station_group = QGroupBox("地面站参数（十进制度）")
        station_layout = QVBoxLayout(station_group)
        station_layout.addWidget(self.station_table)
        station_layout.addLayout(button_layout)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("场景创建和可见性计算过程将在这里显示")
        log_group = QGroupBox("运行信息")
        log_layout = QVBoxLayout(log_group)
        log_layout.addWidget(self.log)

        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(6, 0, 0, 0)
        layout.addWidget(station_group, 3)
        layout.addWidget(log_group, 2)

        self._write_station(
            0,
            StationConfig("ChengDu", 30.572800, 104.066800, 500.0, 15.0),
        )
        return panel

    def _start(self) -> None:
        try:
            request = self._read_request()
            if request.stk_mode == "running":
                answer = QMessageBox.question(
                    self,
                    "连接正在运行的 STK",
                    "创建新场景会关闭当前 STK 场景，是否继续？",
                    QMessageBox.StandardButton.Yes
                    | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if answer != QMessageBox.StandardButton.Yes:
                    return
            self._clear_results()
            self.tabs.setCurrentIndex(0)
            self.controller.start(request)
        except Exception as error:
            QMessageBox.warning(self, "参数错误", str(error))

    def _read_request(self) -> ScenarioRequest:
        scenario_name = self.scenario_name.text().strip()
        satellite_name = self.satellite_name.text().strip()
        tle_url = self.tle_url.text().strip()
        if not scenario_name:
            raise ValueError("场景名称不能为空。")
        if not satellite_name:
            raise ValueError("卫星名称不能为空。")
        if not tle_url:
            raise ValueError("TLE 地址不能为空。")
        start_msec = self.start_time.dateTime().toMSecsSinceEpoch()
        stop_msec = self.stop_time.dateTime().toMSecsSinceEpoch()
        if stop_msec <= start_msec:
            raise ValueError("结束时间必须晚于开始时间。")

        stations = tuple(
            self.station_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            for row in range(self.station_table.rowCount())
        )
        if not stations:
            raise ValueError("至少需要一个地面站。")
        names = [station.name.casefold() for station in stations]
        if len(names) != len(set(names)):
            raise ValueError("地面站名称不能重复。")
        analysis_station_name = self.analysis_station.currentText().strip()
        if not analysis_station_name:
            raise ValueError("请选择用于可见性分析的地面站。")

        return ScenarioRequest(
            stk_mode=str(self.stk_mode.currentData()),
            scenario_name=scenario_name,
            start_time=_stk_time(self.start_time.dateTime()),
            stop_time=_stk_time(self.stop_time.dateTime()),
            satellite_name=satellite_name,
            satellite_ssc=self.satellite_ssc.value(),
            propagation_step_sec=self.propagation_step.value(),
            tle_url=tle_url,
            stations=stations,
            analysis_station_name=analysis_station_name,
            aer_step_sec=self.aer_step.value(),
        )

    def _update_tle_url(self, ssc: int) -> None:
        self.tle_url.setText(TLE_URL.format(ssc=ssc))

    def _add_station(self) -> None:
        number = self.station_table.rowCount() + 1
        dialog = StationDialog(
            self,
            "添加地面站",
            StationConfig(f"GroundStation{number}", 0.0, 0.0, 0.0, 15.0),
        )
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.station:
            self._write_station(self.station_table.rowCount(), dialog.station)

    def _edit_station(self, *_args) -> None:
        row = self.station_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "编辑地面站", "请先选中一个地面站。")
            return
        station = self.station_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        dialog = StationDialog(self, "编辑地面站", station)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.station:
            self._write_station(row, dialog.station)

    def _delete_station(self) -> None:
        row = self.station_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "删除地面站", "请先选中一个地面站。")
            return
        current_name = self.analysis_station.currentText()
        self.station_table.removeRow(row)
        self._refresh_analysis_stations(current_name)

    def _write_station(self, row: int, station: StationConfig) -> None:
        if row == self.station_table.rowCount():
            self.station_table.insertRow(row)
        values = (
            station.name,
            f"{station.latitude_deg:.6f}",
            f"{station.longitude_deg:.6f}",
            f"{station.altitude_m:.2f}",
            f"{station.min_elevation_deg:.2f}",
        )
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            if column > 0:
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.station_table.setItem(row, column, item)
        self.station_table.item(row, 0).setData(Qt.ItemDataRole.UserRole, station)
        self.station_table.selectRow(row)
        self._refresh_analysis_stations(station.name)

    def _refresh_analysis_stations(self, preferred_name: str = "") -> None:
        current_name = preferred_name or self.analysis_station.currentText()
        stations = [
            self.station_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            for row in range(self.station_table.rowCount())
        ]
        self.analysis_station.blockSignals(True)
        self.analysis_station.clear()
        for station in stations:
            self.analysis_station.addItem(station.name)
        index = self.analysis_station.findText(current_name)
        if index >= 0:
            self.analysis_station.setCurrentIndex(index)
        self.analysis_station.blockSignals(False)

    def _set_busy(self, busy: bool) -> None:
        self.settings_widget.setEnabled(not busy)
        self.station_table.setEnabled(not busy)
        self.add_button.setEnabled(not busy)
        self.edit_button.setEnabled(not busy)
        self.delete_button.setEnabled(not busy)
        self.run_button.setEnabled(not busy)
        if busy:
            self.status_label.setText("正在创建场景并计算可见性...")
            self._append_log("开始执行仿真")

    def _append_log(self, message: str) -> None:
        current_time = QTime.currentTime().toString("HH:mm:ss")
        self.log.appendPlainText(f"[{current_time}] {message}")

    def _show_result(self, result) -> None:
        self._fill_access_table(result)
        self._fill_aer_table(result)
        self._plot_result(result)
        interval_count = len(result.access_intervals)
        sample_count = len(result.aer_samples)
        self.status_label.setText(
            f"完成：{result.analysis_station_name} 可见时段 {interval_count} 个，"
            f"AER 采样点 {sample_count} 个"
        )
        self._append_log(
            f"完成：{result.scenario_name}，{result.analysis_station_name} → "
            f"{result.satellite_name}，可见时段 {interval_count} 个"
        )
        self.tabs.setCurrentIndex(3 if sample_count else 1)

    def _fill_access_table(self, result) -> None:
        self.access_table.setRowCount(len(result.access_intervals))
        for row, interval in enumerate(result.access_intervals):
            values = (
                str(interval.access_number),
                interval.start_time,
                interval.stop_time,
                f"{interval.duration_sec:.3f}",
            )
            self._write_result_row(self.access_table, row, values)

    def _fill_aer_table(self, result) -> None:
        self.aer_table.setRowCount(len(result.aer_samples))
        for row, sample in enumerate(result.aer_samples):
            values = (
                str(sample.access_number),
                sample.time,
                f"{sample.azimuth_deg:.6f}",
                f"{sample.elevation_deg:.6f}",
                f"{sample.range_km:.3f}",
            )
            self._write_result_row(self.aer_table, row, values)

    @staticmethod
    def _write_result_row(table: QTableWidget, row: int, values) -> None:
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            if column != 1:
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(row, column, item)

    def _plot_result(self, result) -> None:
        self.figure.clear()
        if not result.aer_samples:
            self._draw_plot_placeholder("所选时段内没有满足最低仰角的可见数据")
            return

        azimuth_axis = self.figure.add_subplot(2, 1, 1)
        elevation_axis = self.figure.add_subplot(
            2, 1, 2, sharex=azimuth_axis
        )
        grouped = defaultdict(list)
        for sample in result.aer_samples:
            grouped[sample.access_number].append(sample)

        for access_number, samples in grouped.items():
            times = [_parse_stk_time(sample.time) for sample in samples]
            if any(value is None for value in times):
                continue
            azimuth_axis.plot(
                times,
                [sample.azimuth_deg for sample in samples],
                color="#1677b8",
                linewidth=1.7,
                label=f"时段 {access_number}",
            )
            elevation_axis.plot(
                times,
                [sample.elevation_deg for sample in samples],
                color="#f28e2b",
                linewidth=1.7,
                label=f"时段 {access_number}",
            )

        if not azimuth_axis.lines:
            self.figure.clear()
            self._draw_plot_placeholder("AER 时间格式无法解析，请查看 AER 数据表")
            return

        azimuth_axis.set_title(
            f"{result.analysis_station_name} → {result.satellite_name} AER 曲线"
        )
        azimuth_axis.set_ylabel("方位角 / °")
        azimuth_axis.set_ylim(0, 360)
        azimuth_axis.set_yticks(range(0, 361, 60))
        azimuth_axis.grid(True, alpha=0.25)

        elevation_axis.axhline(
            result.analysis_min_elevation_deg,
            color="#7f8c8d",
            linestyle="--",
            linewidth=1.2,
            label=f"最低仰角 {result.analysis_min_elevation_deg:g}°",
        )
        elevation_axis.set_ylabel("仰角 / °")
        elevation_axis.set_xlabel("时间 / UTC")
        elevation_axis.set_ylim(0, 90)
        elevation_axis.grid(True, alpha=0.25)

        locator = mdates.AutoDateLocator(minticks=4, maxticks=10)
        elevation_axis.xaxis.set_major_locator(locator)
        elevation_axis.xaxis.set_major_formatter(
            mdates.ConciseDateFormatter(locator)
        )
        elevation_axis.legend(loc="best", fontsize=8, ncol=2)
        self.figure.tight_layout()
        self.canvas.draw_idle()

    def _draw_plot_placeholder(self, message: str) -> None:
        self.figure.clear()
        axis = self.figure.add_subplot(1, 1, 1)
        axis.text(
            0.5,
            0.5,
            message,
            ha="center",
            va="center",
            color="#7a8794",
            transform=axis.transAxes,
        )
        axis.set_axis_off()
        self.canvas.draw_idle()

    def _clear_results(self) -> None:
        self.access_table.setRowCount(0)
        self.aer_table.setRowCount(0)
        self._draw_plot_placeholder("正在计算可见时段和 AER 数据...")

    def _show_error(self, message: str) -> None:
        self.status_label.setText("仿真失败")
        self._append_log(f"失败：{message}")
        QMessageBox.critical(self, "仿真失败", message)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.controller.is_busy:
            QMessageBox.information(self, "任务进行中", "请等待仿真完成。")
            event.ignore()
            return
        self.controller.shutdown()
        event.accept()


def _result_table(headers: tuple[str, ...], stretch_column: int) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setAlternatingRowColors(True)
    header = table.horizontalHeader()
    for column in range(len(headers)):
        mode = (
            QHeaderView.ResizeMode.Stretch
            if column == stretch_column
            else QHeaderView.ResizeMode.ResizeToContents
        )
        header.setSectionResizeMode(column, mode)
    return table


def _number_field(
    value: float,
    minimum: float,
    maximum: float,
    decimals: int,
    step: float,
    suffix: str,
) -> QDoubleSpinBox:
    field = QDoubleSpinBox()
    field.setRange(minimum, maximum)
    field.setDecimals(decimals)
    field.setSingleStep(step)
    field.setSuffix(suffix)
    field.setValue(value)
    return field


def _date_time_field(value: QDateTime) -> QDateTimeEdit:
    field = QDateTimeEdit(value)
    field.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
    field.setCalendarPopup(True)
    return field


def _stk_time(value: QDateTime) -> str:
    utc = value.toUTC()
    months = (
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    )
    date = utc.date()
    clock = utc.time()
    return (
        f"{date.day()} {months[date.month() - 1]} {date.year()} "
        f"{clock.hour():02d}:{clock.minute():02d}:{clock.second():02d}."
        f"{clock.msec():03d}"
    )


def _parse_stk_time(value: str) -> datetime | None:
    text = " ".join(str(value).replace("UTCG", "").split())
    whole, separator, fraction = text.partition(".")
    if separator:
        fraction = "".join(character for character in fraction if character.isdigit())
        text = f"{whole}.{(fraction + '000000')[:6]}"
        time_format = "%d %b %Y %H:%M:%S.%f"
    else:
        time_format = "%d %b %Y %H:%M:%S"
    try:
        return datetime.strptime(text, time_format)
    except ValueError:
        return None


def run_application() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("STK 可见性与 AER 分析")
    app.setWindowIcon(QIcon(str(APP_ICON)))
    app.setStyle("Fusion")
    app.setFont(QFont("Microsoft YaHei UI", 10))
    app.setStyleSheet(STYLE_SHEET)
    window = MainWindow()
    window.show()
    return app.exec()
