"""STK 场景、卫星和地面站创建界面。"""

from __future__ import annotations

import sys

from PySide6.QtCore import QDateTime, QTime, Qt
from PySide6.QtGui import QCloseEvent, QFont
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
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from stk_aer_analysis.controller import ScenarioController
from stk_aer_analysis.models import ScenarioRequest, StationConfig


TLE_URL = "https://celestrak.org/NORAD/elements/gp.php?CATNR={ssc}&FORMAT=TLE"

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
        self.resize(1180, 760)
        self.setMinimumSize(980, 650)

        self.controller = ScenarioController(self)
        self.controller.busy_changed.connect(self._set_busy)
        self.controller.progress.connect(self._append_log)
        self.controller.completed.connect(self._show_result)
        self.controller.failed.connect(self._show_error)

        title = QLabel("STK 可见性与 AER 分析")
        title.setObjectName("titleLabel")
        subtitle = QLabel("第一阶段：自动创建场景、01A 卫星和地面站")
        subtitle.setObjectName("statusLabel")

        self.settings_widget = self._build_settings()
        stations_widget = self._build_stations()
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.settings_widget)
        splitter.addWidget(stations_widget)
        splitter.setSizes([430, 720])

        self.status_label = QLabel("等待创建场景")
        self.status_label.setObjectName("statusLabel")
        self.run_button = QPushButton("连接 STK 并创建场景")
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
        layout.addWidget(splitter, 1)
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
        scenario_form.addRow("开始时间（本地）", self.start_time)
        scenario_form.addRow("结束时间（本地）", self.stop_time)

        self.satellite_name = QLineEdit("TN01A")
        self.satellite_ssc = QSpinBox()
        self.satellite_ssc.setRange(1, 999999)
        self.satellite_ssc.setValue(59705)
        self.propagation_step = _number_field(60.0, 1.0, 3600.0, 1, 10.0, " s")
        self.tle_url = QLineEdit(TLE_URL.format(ssc=59705))
        self.satellite_ssc.valueChanged.connect(self._update_tle_url)

        satellite_group = QGroupBox("01A 卫星参数")
        satellite_form = QFormLayout(satellite_group)
        satellite_form.addRow("卫星名称", self.satellite_name)
        satellite_form.addRow("SSC 编号", self.satellite_ssc)
        satellite_form.addRow("传播步长", self.propagation_step)
        satellite_form.addRow("TLE 地址", self.tle_url)

        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 6, 0)
        layout.addWidget(connection_group)
        layout.addWidget(scenario_group)
        layout.addWidget(satellite_group)
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

        station_group = QGroupBox("地面站参数")
        station_layout = QVBoxLayout(station_group)
        station_layout.addWidget(self.station_table)
        station_layout.addLayout(button_layout)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("创建过程将在这里显示")
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
            StationConfig("LinGang", 30.90361111, 121.91944444, 0.0, 15.0),
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
        self.station_table.removeRow(row)

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

    def _set_busy(self, busy: bool) -> None:
        self.settings_widget.setEnabled(not busy)
        self.station_table.setEnabled(not busy)
        self.add_button.setEnabled(not busy)
        self.edit_button.setEnabled(not busy)
        self.delete_button.setEnabled(not busy)
        self.run_button.setEnabled(not busy)
        if busy:
            self.status_label.setText("正在创建 STK 场景...")
            self._append_log("开始创建场景")

    def _append_log(self, message: str) -> None:
        current_time = QTime.currentTime().toString("HH:mm:ss")
        self.log.appendPlainText(f"[{current_time}] {message}")

    def _show_result(self, result) -> None:
        self.status_label.setText("STK 场景创建完成")
        self._append_log(
            f"完成：{result.scenario_name}，卫星 {result.satellite_name}，"
            f"地面站 {result.station_count} 个"
        )
        QMessageBox.information(
            self,
            "创建完成",
            f"场景：{result.scenario_name}\n"
            f"时间：{result.start_time} 至 {result.stop_time}\n"
            f"卫星：{result.satellite_name}（{result.tle_name}）\n"
            f"地面站：{result.station_count} 个",
        )

    def _show_error(self, message: str) -> None:
        self.status_label.setText("场景创建失败")
        self._append_log(f"失败：{message}")
        QMessageBox.critical(self, "创建失败", message)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.controller.is_busy:
            QMessageBox.information(self, "任务进行中", "请等待场景创建完成。")
            event.ignore()
            return
        self.controller.shutdown()
        event.accept()


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
    months = (
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    )
    date = value.date()
    clock = value.time()
    return (
        f"{date.day()} {months[date.month() - 1]} {date.year()} "
        f"{clock.hour():02d}:{clock.minute():02d}:{clock.second():02d}."
        f"{clock.msec():03d}"
    )


def run_application() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("STK 可见性与 AER 分析")
    app.setStyle("Fusion")
    app.setFont(QFont("Microsoft YaHei UI", 10))
    app.setStyleSheet(STYLE_SHEET)
    window = MainWindow()
    window.show()
    return app.exec()
