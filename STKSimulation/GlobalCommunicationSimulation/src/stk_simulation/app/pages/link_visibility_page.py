"""星地建链与 AER 预报桌面端功能页（复刻 SatLog 原版：双地点卡 + 4 指标卡 + 窗口表 + AER 下载 + 世界地图动画）。

去除：极坐标天空图、独立仰角折线图、双引擎对比看板。
"""

from __future__ import annotations

from bisect import bisect_right
import copy
import csv
from datetime import timedelta
from math import isfinite

from PySide6.QtCore import QElapsedTimer, QPointF, QSignalBlocker, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QPageLayout, QPainter, QPen, QPixmap, QPolygonF, QTextDocument
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDateEdit,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QScrollArea,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from stk_simulation.app.icons import action_button, apply_icon
from stk_simulation.app.widgets.orbit_globe import (
    OrbitGlobeWidget, SATELLITE_COLOR, SPACE_COLOR, STATION_COLORS, world_rings,
)
from stk_simulation.app.widgets.side_navigation import SideNavigation
from stk_simulation.simulations.common import SatelliteConfig
from stk_simulation.simulations.link_visibility.config import (
    LinkStationConfig,
    LinkVisibilityConfig,
    LinkVisibilityResult,
)

class WorldMapWidget(QWidget):
    """星下点地图。底图和完整轨迹只在数据或尺寸变化时重绘。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(440)
        self._track = ()
        self._stations = ()
        self._position = 0.0
        self._cache_key = None
        self._background = QPixmap()

    def set_data(self, track, stations) -> None:
        self._track = track
        self._stations = tuple(stations[:2])
        self._position = 0.0
        self._cache_key = None
        self.update()

    def set_position(self, position: float) -> None:
        self._position = position
        self.update()

    def _project(self, lon: float, lat: float) -> QPointF:
        # 锁定 2:1（360°×180°）等距圆柱投影，避免窗口过宽时把地球横向拉扁
        width = float(self.width())
        height = float(self.height())
        map_h = min(height, width / 2.0)
        map_w = map_h * 2.0
        offset_x = (width - map_w) / 2.0
        offset_y = (height - map_h) / 2.0
        x = offset_x + (lon + 180.0) / 360.0 * map_w
        y = offset_y + (90.0 - lat) / 180.0 * map_h
        return QPointF(x, y)

    def _make_background(self, scale: float) -> QPixmap:
        image = QPixmap(round(self.width() * scale), round(self.height() * scale))
        image.setDevicePixelRatio(scale)
        image.fill(QColor(SPACE_COLOR))
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor("#324963"), 0.7))
        for ring in world_rings():
            painter.drawPolyline(QPolygonF([self._project(lon, lat) for lon, lat in ring]))

        painter.setPen(QPen(QColor(34, 211, 238), 1.6))
        segment = []
        prev_lon = None
        for point in self._track:
            lon, lat = point.longitude_deg, point.latitude_deg
            valid = isfinite(lon) and isfinite(lat)
            if not valid or (prev_lon is not None and abs(lon - prev_lon) > 180):
                painter.drawPolyline(QPolygonF(segment))
                segment.clear()
            if valid:
                segment.append(self._project(lon, lat))
            prev_lon = lon if valid else None
        painter.drawPolyline(QPolygonF(segment))

        for station, color in zip(self._stations, STATION_COLORS):
            pos = self._project(station.longitude_deg, station.latitude_deg)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(color))
            painter.drawEllipse(pos, 6, 6)
            painter.setPen(QColor(color))
            painter.drawText(pos + QPointF(9, 4), station.name)
        painter.end()
        return image

    def _draw_satellite(self, painter) -> None:
        start = int(self._position)
        a = self._track[start]
        b = self._track[min(start + 1, len(self._track) - 1)]
        fraction = self._position - start
        delta_lon = (b.longitude_deg - a.longitude_deg + 180) % 360 - 180
        lon = (a.longitude_deg + delta_lon * fraction + 180) % 360 - 180
        lat = a.latitude_deg + (b.latitude_deg - a.latitude_deg) * fraction
        if not (isfinite(lon) and isfinite(lat)):
            return
        satellite = self._project(lon, lat)
        for station, linked, color in zip(self._stations, (a.linked1, a.linked2), STATION_COLORS):
            if linked:
                painter.setPen(QPen(QColor(color), 2.0))
                painter.drawLine(self._project(station.longitude_deg, station.latitude_deg), satellite)

        painter.setPen(QPen(QColor("#674c16"), 2))
        painter.setBrush(QColor(SATELLITE_COLOR))
        painter.drawEllipse(satellite, 7, 7)

    def paintEvent(self, _event) -> None:
        scale = self.devicePixelRatioF()
        key = (self.width(), self.height(), scale)
        if key != self._cache_key:
            self._background = self._make_background(scale)
            self._cache_key = key
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._background)
        if self._track:
            painter.setRenderHint(QPainter.Antialiasing)
            self._draw_satellite(painter)
        painter.end()


def _metric_card(title: str) -> tuple[QFrame, QLabel, QLabel]:
    card = QFrame()
    card.setObjectName("gainSummary")
    layout = QVBoxLayout(card)
    label = QLabel(title)
    label.setObjectName("statusLabel")
    value = QLabel("—")
    value.setStyleSheet("font-size:22px;font-weight:600;color:#2563eb;")
    layout.addWidget(label)
    layout.addWidget(value)
    return card, value, label


def _fill_table(table: QTableWidget, headers: tuple[str, ...], rows) -> None:
    table.verticalHeader().hide()
    table.setAlternatingRowColors(True)
    table.setShowGrid(False)
    table.setRowCount(len(rows))
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(list(headers))
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            table.setItem(r, c, QTableWidgetItem(str(value)))
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)


class LinkVisibilityPage(QWidget):
    run_requested = Signal(object, str)

    def __init__(self, default_config: LinkVisibilityConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = copy.deepcopy(default_config)
        self._last_result: LinkVisibilityResult | None = None
        self._sample_times: tuple[float, ...] = ()
        self._elapsed_sec = 0.0
        self._play_speed = 600
        self._clock = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._advance_track)
        self._build_ui()

    # ---------------------------------------------------------------- UI
    def _build_ui(self) -> None:
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(14)
        self.sections = QStackedWidget()
        settings = QWidget()
        parameters = QVBoxLayout(settings)
        parameters.setSpacing(10)
        loc_row = QHBoxLayout()
        loc_row.addWidget(self._build_loc_card(0))
        loc_row.addWidget(self._build_loc_card(1))
        parameters.addLayout(loc_row)
        parameters.addWidget(self._build_compute_bar())
        parameters.addStretch(1)
        self.sections.addWidget(self._scroll(settings))

        results = QWidget()
        root = QVBoxLayout(results)
        self.run_context = QLabel()
        self.run_context.setObjectName("hintLabel")
        self.run_context.setWordWrap(True)
        self.run_context.hide()
        root.addWidget(self.run_context)

        # 4 张指标卡
        metrics_row = QHBoxLayout()
        self.metric_comm_card, self.metric_comm_val, _ = _metric_card("两地通信窗口数")
        self.metric_dur_card, self.metric_dur_val, _ = _metric_card("累计通信时长")
        self.metric_p1_card, self.metric_p1_val, _ = _metric_card("地点 1 可用时长")
        self.metric_p2_card, self.metric_p2_val, _ = _metric_card("地点 2 可用时长")
        for card in (self.metric_comm_card, self.metric_dur_card, self.metric_p1_card, self.metric_p2_card):
            metrics_row.addWidget(card)
        root.addLayout(metrics_row)

        # 窗口表
        self.comm_table = QTableWidget()
        root.addWidget(self._section("两地通信窗口", self.comm_table))
        loc_tables = QHBoxLayout()
        self.p1_table = QTableWidget()
        self.p2_table = QTableWidget()
        loc_tables.addWidget(self._section("地点 1 可用窗口", self.p1_table))
        loc_tables.addWidget(self._section("地点 2 可用窗口", self.p2_table))
        root.addLayout(loc_tables)

        # AER 数据下载：对象（地点1/地点2/两地通信）× 窗口 × 格式（CSV/PDF）
        dl_card = QGroupBox("AER 数据下载")
        dl_layout = QVBoxLayout(dl_card)
        dl_row = QHBoxLayout()
        dl_row.addWidget(QLabel("对象"))
        self.dl_group = QComboBox()
        dl_row.addWidget(self.dl_group)
        dl_row.addWidget(QLabel("窗口"))
        self.dl_win = QComboBox()
        dl_row.addWidget(self.dl_win)
        dl_row.addWidget(QLabel("格式"))
        self.dl_fmt = QComboBox()
        self.dl_fmt.addItem("CSV", "csv")
        self.dl_fmt.addItem("PDF", "pdf")
        dl_row.addWidget(self.dl_fmt)
        self.dl_btn = action_button("下载", "download", primary=True)
        self.dl_btn.setEnabled(False)
        self.dl_btn.clicked.connect(self._export_selected)
        dl_row.addWidget(self.dl_btn)
        self.dl_info = QLabel("—")
        self.dl_info.setObjectName("hintLabel")
        dl_row.addWidget(self.dl_info, 1)
        dl_layout.addLayout(dl_row)
        self.dl_preview = QTableWidget()
        self.dl_preview.setMaximumHeight(280)
        dl_layout.addWidget(self.dl_preview)
        root.addWidget(dl_card)

        self._downloads: list[dict] = []
        self.dl_group.currentIndexChanged.connect(self._refresh_win_options)
        self.dl_win.currentIndexChanged.connect(self._refresh_preview)
        root.addStretch(1)
        self.sections.addWidget(self._scroll(results))

        self.sections.addWidget(self._scroll(self._build_track_tab()))

        self.status_label = QLabel("就绪：等待启动建链计算")
        self.status_label.setObjectName("statusLabel")
        panel = QFrame()
        panel.setObjectName("toolPanel")
        content = QVBoxLayout(panel)
        content.setContentsMargins(11, 10, 11, 11)
        content.addWidget(self.sections, 1)
        content.addWidget(self.status_label)
        outer.addWidget(SideNavigation((
            ("站点与时段", "radio-tower"), ("窗口与下载", "download"),
            ("轨迹地图", "globe"),
        ), self.sections))
        outer.addWidget(panel, 1)

    def _build_track_tab(self) -> QWidget:
        map_card = QGroupBox("卫星轨迹")
        map_layout = QVBoxLayout(map_card)
        self.map_widget = WorldMapWidget()
        self.globe_widget = OrbitGlobeWidget()
        self.track_views = QStackedWidget()
        self.track_views.addWidget(self.map_widget)
        self.track_views.addWidget(self.globe_widget)
        modes = QHBoxLayout()
        group = QButtonGroup(map_card)
        for index, (caption, artwork) in enumerate((("二维地图", "globe"), ("三维轨道", "orbit"))):
            button = action_button(caption, artwork)
            button.setCheckable(True)
            group.addButton(button, index)
            modes.addWidget(button)
        group.button(0).setChecked(True)
        group.idClicked.connect(self.track_views.setCurrentIndex)
        modes.addStretch(1)
        hint = QLabel("拖动旋转 · 滚轮缩放")
        hint.setObjectName("hintLabel")
        hint.hide()
        self.track_views.currentChanged.connect(lambda index: hint.setVisible(index == 1))
        modes.addWidget(hint)
        map_layout.addLayout(modes)
        map_layout.addWidget(self.track_views, 1)

        ctrl = QHBoxLayout()
        self.btn_play = action_button("动画播放", "play")
        self.btn_play.clicked.connect(self._toggle_play)
        self.btn_reset = action_button("重置", "rotate-ccw")
        self.btn_reset.clicked.connect(self._reset_track)
        self.speed_combo = QComboBox()
        for value in ("60", "300", "600", "1200", "3600"):
            self.speed_combo.addItem(f"{value}×", int(value))
        self.speed_combo.setCurrentIndex(2)
        self.speed_combo.currentIndexChanged.connect(self._on_speed)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 0)
        self.slider.valueChanged.connect(self._on_slider)
        self.map_status = QLabel("完成计算后可播放")
        self.map_status.setObjectName("statusLabel")
        ctrl.addWidget(self.btn_play)
        ctrl.addWidget(self.btn_reset)
        ctrl.addWidget(QLabel("动画速度"))
        ctrl.addWidget(self.speed_combo)
        ctrl.addWidget(self.slider, 1)
        ctrl.addWidget(self.map_status)
        map_layout.addLayout(ctrl)
        self._update_play_button()
        self.btn_reset.setEnabled(False)
        self.slider.setEnabled(False)
        return map_card

    @staticmethod
    def _scroll(content: QWidget) -> QScrollArea:
        widget = QScrollArea()
        widget.setObjectName("toolScroll")
        widget.setWidgetResizable(True)
        widget.setFrameShape(QFrame.Shape.NoFrame)
        content.setObjectName("toolScrollContent")
        widget.setWidget(content)
        return widget

    def _section(self, title: str, widget: QWidget) -> QWidget:
        group = QGroupBox(title)
        layout = QVBoxLayout(group)
        layout.addWidget(widget)
        return group

    def _build_loc_card(self, index: int) -> QWidget:
        st = self._config.stations[index]
        card = QGroupBox(f"地点 {index + 1}")
        form = QFormLayout(card)

        name_edit = QLineEdit(st.name)
        form.addRow("名称", name_edit)

        mode_combo = QComboBox()
        mode_combo.addItem("十进制", "decimal")
        mode_combo.addItem("度分秒", "dms")
        form.addRow("坐标格式", mode_combo)

        stacked = QStackedWidget()
        # 十进制
        dec_widget = QWidget()
        dec = QFormLayout(dec_widget)
        lat_dec = _spin(-90.0, 90.0, st.latitude_deg, 6)
        lon_dec = _spin(-180.0, 180.0, st.longitude_deg, 6)
        dec.addRow("纬度 (°)", lat_dec)
        dec.addRow("经度 (°)", lon_dec)
        # 度分秒
        dms_widget = QWidget()
        dms = QFormLayout(dms_widget)
        lat_deg = _int_spin(0, 90, int(st.latitude_deg))
        lat_min = _int_spin(0, 59, 0)
        lat_sec = _int_spin(0, 59, 0)
        lon_deg = _int_spin(0, 180, int(st.longitude_deg))
        lon_min = _int_spin(0, 59, 0)
        lon_sec = _int_spin(0, 59, 0)
        dms.addRow("纬度 度/分/秒", _three(lat_deg, lat_min, lat_sec))
        dms.addRow("经度 度/分/秒", _three(lon_deg, lon_min, lon_sec))
        stacked.addWidget(dec_widget)
        stacked.addWidget(dms_widget)
        form.addRow("", stacked)
        mode_combo.currentIndexChanged.connect(
            lambda i: stacked.setCurrentIndex(0 if mode_combo.itemData(i) == "decimal" else 1)
        )
        mode_combo.setCurrentIndex(0)
        stacked.setCurrentIndex(0)

        min_el = _spin(0.0, 85.0, st.min_elevation_deg, 2)
        gso = _spin(0.0, 45.0, st.gso_avoid_deg, 2)
        form.addRow("最低仰角 (°)", min_el)
        form.addRow("GSO 隔离角 (°)", gso)

        setattr(self, f"_loc{index}", {
            "name": name_edit, "mode": mode_combo, "stack": stacked,
            "lat_dec": lat_dec, "lon_dec": lon_dec,
            "lat_deg": lat_deg, "lat_min": lat_min, "lat_sec": lat_sec,
            "lon_deg": lon_deg, "lon_min": lon_min, "lon_sec": lon_sec,
            "min_el": min_el, "gso": gso,
        })
        return card

    def _build_compute_bar(self) -> QWidget:
        card = QGroupBox("计算控制")
        layout = QHBoxLayout(card)
        layout.addWidget(QLabel("开始日期"))
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(self.date_edit.date().currentDate())
        layout.addWidget(self.date_edit)
        layout.addWidget(QLabel("计算天数"))
        self.days_spin = QSpinBox()
        self.days_spin.setRange(1, 8)
        self.days_spin.setValue(1)
        layout.addWidget(self.days_spin)
        self.run_btn = action_button("计算两地通信时长", "play", primary=True)
        self.run_btn.clicked.connect(lambda: self._emit_run())
        layout.addStretch(1)
        layout.addWidget(self.run_btn)
        return card

    # ---------------------------------------------------------------- 动作
    def set_reference_satellite(self, profile) -> None:
        self._config.satellite = SatelliteConfig.from_reference(profile, self._config.satellite.step)
        self._config.tle_file = ""

    def _read_loc(self, index: int) -> LinkStationConfig:
        loc = getattr(self, f"_loc{index}")
        st = self._config.stations[index]
        if loc["mode"].currentData() == "decimal":
            lat = loc["lat_dec"].value()
            lon = loc["lon_dec"].value()
        else:
            lat = loc["lat_deg"].value() + loc["lat_min"].value() / 60.0 + loc["lat_sec"].value() / 3600.0
            lon = loc["lon_deg"].value() + loc["lon_min"].value() / 60.0 + loc["lon_sec"].value() / 3600.0
        return LinkStationConfig(
            name=loc["name"].text().strip() or st.name,
            latitude_deg=lat,
            longitude_deg=lon,
            altitude_m=st.altitude_m,
            min_elevation_deg=loc["min_el"].value(),
            gso_avoid_deg=loc["gso"].value(),
        )

    def _emit_run(self) -> None:
        cfg = copy.deepcopy(self._config)
        cfg.stations[0] = self._read_loc(0)
        cfg.stations[1] = self._read_loc(1)
        start = self.date_edit.date().toPython()
        stop = start + timedelta(days=self.days_spin.value())
        cfg.scenario.start_time = f"{start:%Y-%m-%d} 00:00:00"
        cfg.scenario.stop_time = f"{stop:%Y-%m-%d} 00:00:00"
        cfg.stk.engine = "python"
        self.status_label.setText("正在计算...")
        self.run_requested.emit(cfg, "normal")

    def _toggle_play(self) -> None:
        if self._timer.isActive():
            self._advance_track()
            self._timer.stop()
        else:
            if self._elapsed_sec >= self._sample_times[-1]:
                self._seek_track(0.0)
            self._clock.start()
            self._timer.start()
        self._update_play_button()

    def _advance_track(self) -> None:
        elapsed = self._clock.restart() / 1000.0
        self._seek_track(self._elapsed_sec + elapsed * self._play_speed)
        if self._elapsed_sec >= self._sample_times[-1]:
            self._timer.stop()
            self._update_play_button()

    def _reset_track(self) -> None:
        self._timer.stop()
        self._seek_track(0.0)
        self._update_play_button()

    def _on_slider(self, value: int) -> None:
        self._seek_track(self._sample_times[value])
        if self._timer.isActive():
            self._clock.restart()
        self._update_play_button()

    def _on_speed(self) -> None:
        if self._timer.isActive():
            self._advance_track()
        self._play_speed = self.speed_combo.currentData()

    def _update_play_button(self) -> None:
        playing = self._timer.isActive()
        self.btn_play.setEnabled(len(self._sample_times) > 1)
        text = "动画播放"
        if playing:
            text = "暂停"
        elif self._elapsed_sec > 0:
            text = "重新播放" if self._elapsed_sec >= self._sample_times[-1] else "继续播放"
        self.btn_play.setText(text)
        apply_icon(self.btn_play, "pause" if playing else "play")

    def _seek_track(self, elapsed_sec: float) -> None:
        if not self._sample_times:
            self.map_status.setText("暂无轨迹数据")
            return
        self._elapsed_sec = min(elapsed_sec, self._sample_times[-1])
        index = bisect_right(self._sample_times, self._elapsed_sec) - 1
        position = float(index)
        if index + 1 < len(self._sample_times):
            start, end = self._sample_times[index:index + 2]
            position += (self._elapsed_sec - start) / (end - start)
        self.map_widget.set_position(position)
        self.globe_widget.set_position(position)
        with QSignalBlocker(self.slider):
            self.slider.setValue(index)
        pt = self._last_result.ground_track[index]
        self.map_status.setText(f"{pt.time}　{'通信中' if pt.linked else '未建链'}")

    def _set_track(self, result: LinkVisibilityResult) -> None:
        self._timer.stop()
        self._elapsed_sec = 0.0
        orbit = result.orbit_track
        self._sample_times = orbit.elapsed_sec if orbit else tuple(
            index * max(5.0, result.cfg.coarse_step_sec) for index in range(len(result.ground_track))
        )
        self.map_widget.set_data(result.ground_track, result.cfg.stations)
        self.globe_widget.set_data(orbit, result.cfg.stations, result.satellite_name)
        with QSignalBlocker(self.slider):
            self.slider.setRange(0, max(len(self._sample_times) - 1, 0))
        self.slider.setEnabled(len(self._sample_times) > 1)
        self.btn_reset.setEnabled(len(self._sample_times) > 1)
        self._seek_track(0.0)
        self._update_play_button()

    def set_busy(self, busy: bool) -> None:
        self.run_btn.setEnabled(not busy)

    def set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def show_result(self, result: LinkVisibilityResult) -> None:
        self._last_result = result
        self.run_context.setText(f"卫星 {result.satellite_name} · {result.start_time} 至 {result.stop_time}")
        self.run_context.show()
        self.sections.setCurrentIndex(1)
        self._build_downloads(result)

        # 指标卡
        self.metric_comm_val.setText(str(len(result.windows)))
        self.metric_dur_val.setText(f"{result.total_duration_sec / 3600.0:.2f} h")
        p1, p2 = result.station_names[0], result.station_names[1] if len(result.station_names) > 1 else ""
        self.metric_p1_val.setText(f"{result.station_totals.get(p1, 0.0) / 3600.0:.2f} h")
        self.metric_p2_val.setText(f"{result.station_totals.get(p2, 0.0) / 3600.0:.2f} h")

        # 窗口表
        _fill_table(self.comm_table,
                    ("序号", "开始", "结束", "时长(秒)", "最高仰角(°)", "峰值时刻"),
                    [(w.access_number, w.start_time, w.stop_time, f"{w.duration_sec:.1f}", f"{w.max_elevation_deg:.2f}", w.max_elevation_time) for w in result.windows])
        self._fill_station_table(self.p1_table, p1)
        self._fill_station_table(self.p2_table, p2)

        # 地图动画
        self._set_track(result)

        self.set_status(f"计算完成：两地 {len(result.windows)} 个窗口，累计 {result.total_duration_sec / 3600.0:.2f} h")

    def _fill_station_table(self, table: QTableWidget, name: str) -> None:
        if not self._last_result:
            return
        windows = self._last_result.station_windows.get(name, ())
        _fill_table(table,
                    ("序号", "开始", "结束", "时长(秒)", "最高仰角(°)"),
                    [(w.access_number, w.start_time, w.stop_time, f"{w.duration_sec:.1f}", f"{w.max_elevation_deg:.2f}") for w in windows])

    # ---------------------------------------------------------------- AER 下载
    def _build_downloads(self, result: LinkVisibilityResult) -> None:
        p1 = result.station_names[0] if result.station_names else "地点1"
        p2 = result.station_names[1] if len(result.station_names) > 1 else "地点2"
        downloads: list[dict] = []

        # 两地通信：宽表（时间 + 地点1 AER + 地点2 AER 并排）
        comm_header = (
            "时间(北京时间)",
            f"{p1}方位角(°)", f"{p1}仰角(°)", f"{p1}距离(km)",
            f"{p2}方位角(°)", f"{p2}仰角(°)", f"{p2}距离(km)",
        )
        for w in result.windows:
            samples = [r for r in result.aer_records if r.access_number == w.access_number]
            by_time: dict[str, dict] = {}
            for r in samples:
                by_time.setdefault(r.time, {})["1" if r.station_name == p1 else "2"] = r
            rows = []
            for time_str, entry in sorted(by_time.items()):
                a = entry.get("1")
                b = entry.get("2")
                rows.append((
                    time_str,
                    f"{a.azimuth_deg:.2f}" if a else "", f"{a.elevation_deg:.2f}" if a else "", f"{a.range_km:.2f}" if a else "",
                    f"{b.azimuth_deg:.2f}" if b else "", f"{b.elevation_deg:.2f}" if b else "", f"{b.range_km:.2f}" if b else "",
                ))
            downloads.append({"group": "两地通信", "win": f"窗口 {w.access_number}", "header": comm_header, "rows": rows})

        # 单站：地点1 / 地点2
        single_header = ("时间(北京时间)", "方位角(°)", "仰角(°)", "距离(km)")
        for name in (p1, p2):
            aer = result.station_aer.get(name, ())
            for w in result.station_windows.get(name, ()):
                rows = [
                    (r.time, f"{r.azimuth_deg:.2f}", f"{r.elevation_deg:.2f}", f"{r.range_km:.2f}")
                    for r in aer if r.access_number == w.access_number
                ]
                downloads.append({"group": name, "win": f"窗口 {w.access_number}", "header": single_header, "rows": rows})

        self._downloads = downloads
        self.dl_group.blockSignals(True)
        self.dl_group.clear()
        groups: list[str] = []
        for entry in downloads:
            if entry["group"] not in groups:
                groups.append(entry["group"])
        for group in groups:
            self.dl_group.addItem(group)
        self.dl_group.blockSignals(False)
        self._refresh_win_options()

    def _refresh_win_options(self) -> None:
        group = self.dl_group.currentText()
        wins = [entry["win"] for entry in self._downloads if entry["group"] == group]
        self.dl_win.blockSignals(True)
        self.dl_win.clear()
        for win in wins:
            self.dl_win.addItem(win)
        self.dl_win.blockSignals(False)
        self._refresh_preview()

    def _current_download(self) -> dict | None:
        group, win = self.dl_group.currentText(), self.dl_win.currentText()
        for entry in self._downloads:
            if entry["group"] == group and entry["win"] == win:
                return entry
        return None

    def _refresh_preview(self) -> None:
        entry = self._current_download()
        if entry is None:
            self.dl_preview.clear()
            self.dl_preview.setRowCount(0)
            self.dl_preview.setColumnCount(0)
            self.dl_btn.setEnabled(False)
            self.dl_info.setText("—")
            return
        header = entry["header"]
        rows = entry["rows"][:500]
        self.dl_preview.setColumnCount(len(header))
        self.dl_preview.setHorizontalHeaderLabels(list(header))
        self.dl_preview.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                self.dl_preview.setItem(r, c, QTableWidgetItem(str(value)))
        self.dl_preview.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.dl_btn.setEnabled(bool(rows))
        suffix = "（预览前 500 行）" if len(entry["rows"]) > 500 else ""
        self.dl_info.setText(f"{entry['group']} · {entry['win']}：共 {len(entry['rows'])} 行{suffix}")

    def _export_selected(self) -> None:
        entry = self._current_download()
        if entry is None:
            return
        fmt = self.dl_fmt.currentData()
        stem = f"AER_{entry['group']}_{entry['win']}".replace(" ", "")
        if fmt == "csv":
            path, _ = QFileDialog.getSaveFileName(self, "导出 AER CSV", f"{stem}.csv", "CSV Files (*.csv)")
            if not path:
                return
            with open(path, "w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(entry["header"])
                for row in entry["rows"]:
                    writer.writerow(row)
            QMessageBox.information(self, "导出成功", f"AER CSV 已保存至：\n{path}")
        else:
            path, _ = QFileDialog.getSaveFileName(self, "导出 AER PDF", f"{stem}.pdf", "PDF Files (*.pdf)")
            if not path:
                return
            self._write_pdf(path, entry)
            QMessageBox.information(self, "导出成功", f"AER PDF 已保存至：\n{path}")

    def _write_pdf(self, path: str, entry: dict) -> None:
        document = QTextDocument()
        html = [
            "<html><body>",
            f"<h3>AER 数据 —— {entry['group']} · {entry['win']}</h3>",
            "<table border='1' cellspacing='0' cellpadding='4' width='100%'>",
            "<tr>" + "".join(f"<th>{head}</th>" for head in entry["header"]) + "</tr>",
        ]
        for row in entry["rows"]:
            html.append("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>")
        html.append("</table></body></html>")
        document.setHtml("".join(html))
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(path)
        printer.setPageOrientation(QPageLayout.Orientation.Landscape)
        document.print_(printer)


def _spin(minimum: float, maximum: float, value: float, decimals: int):
    from PySide6.QtWidgets import QDoubleSpinBox
    box = QDoubleSpinBox()
    box.setRange(minimum, maximum)
    box.setDecimals(decimals)
    box.setValue(value)
    return box


def _int_spin(minimum: int, maximum: int, value: int):
    box = QSpinBox()
    box.setRange(minimum, maximum)
    box.setValue(value)
    return box


def _three(a, b, c) -> QWidget:
    widget = QWidget()
    layout = QHBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(a)
    layout.addWidget(b)
    layout.addWidget(c)
    return widget
