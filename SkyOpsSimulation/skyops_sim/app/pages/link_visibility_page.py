"""星地建链可见性、AER 导出和轨迹播放页面。"""

from __future__ import annotations

from bisect import bisect_right
import copy
from datetime import timedelta
from itertools import chain, islice
from math import isfinite

from PySide6.QtCore import QElapsedTimer, QEvent, QPointF, QSignalBlocker, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (
    QBoxLayout,
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

from skyops_sim.app.aer_export import build_aer_groups, write_aer_csv, write_aer_pdf
from skyops_sim.app.icons import action_button, apply_icon
from skyops_sim.app.widgets.orbit_globe import (
    OrbitGlobeWidget, SATELLITE_COLOR, SPACE_COLOR, STATION_COLORS, world_rings,
)
from skyops_sim.app.widgets.side_navigation import SideNavigation
from skyops_sim.simulations.common import SatelliteConfig
from skyops_sim.simulations.link_visibility.config import (
    LinkStationConfig,
    LinkVisibilityConfig,
    LinkVisibilityResult,
)

class WorldMapWidget(QWidget):
    """星下点地图。底图和完整轨迹只在数据或尺寸变化时重绘。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(360)
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


_WINDOW_METRIC_COLUMNS = (3, 4)


def _metric_card(title: str, *, emphasized: bool = False) -> tuple[QFrame, QLabel]:
    card = QFrame()
    card.setObjectName("metricCard")
    layout = QVBoxLayout(card)
    label = QLabel(title)
    label.setObjectName("fieldCaption")
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    value = QLabel("—")
    value.setObjectName("metricValue")
    value.setProperty("emphasized", emphasized)
    value.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(label)
    layout.addWidget(value)
    return card, value


def _fill_window_table(table: QTableWidget, headers: tuple[str, ...], rows) -> None:
    table.verticalHeader().hide()
    table.setAlternatingRowColors(True)
    table.setShowGrid(True)
    table.setWordWrap(False)
    table.setRowCount(len(rows))
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(list(headers))
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            item = QTableWidgetItem(str(value))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(r, c, item)
    header = table.horizontalHeader()
    header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
    header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    for column in _WINDOW_METRIC_COLUMNS:
        header.setSectionResizeMode(column, QHeaderView.ResizeMode.Stretch)


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
        comm_card, self.metric_comm_val = _metric_card("两地通信窗口数")
        duration_card, self.metric_dur_val = _metric_card("累计通信时长", emphasized=True)
        station_1_card, self.metric_p1_val = _metric_card("地点 1 可用时长")
        station_2_card, self.metric_p2_val = _metric_card("地点 2 可用时长")
        for card in (comm_card, duration_card, station_1_card, station_2_card):
            metrics_row.addWidget(card, 1)
        root.addLayout(metrics_row)

        # 窗口表
        self.comm_table = QTableWidget()
        root.addWidget(self._section("两地通信窗口", self.comm_table))
        self.p1_table = QTableWidget()
        self.p2_table = QTableWidget()
        self.station_tables = QWidget()
        self.station_layout = QBoxLayout(QBoxLayout.Direction.LeftToRight, self.station_tables)
        self.station_layout.setContentsMargins(0, 0, 0, 0)
        self.station_groups = (
            self._section("地点 1 可用窗口", self.p1_table),
            self._section("地点 2 可用窗口", self.p2_table),
        )
        for group in self.station_groups:
            self.station_layout.addWidget(group, 1)
        self.station_tables.installEventFilter(self)
        root.addWidget(self.station_tables)

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
        map_card = QWidget()
        map_layout = QVBoxLayout(map_card)
        self.map_widget = WorldMapWidget()
        self.globe_widget = OrbitGlobeWidget()
        views = QHBoxLayout()
        views.setSpacing(12)
        ground_map = self._section("二维星下点", self.map_widget)
        orbit = self._section("三维轨道", self.globe_widget)
        views.addWidget(ground_map, 1)
        views.addWidget(orbit, 1)
        map_layout.addLayout(views, 1)

        ctrl = QHBoxLayout()
        self.btn_play = action_button("动画播放", "play")
        self.btn_play.setMinimumWidth(112)
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
        hint = QLabel("三维轨道可拖动旋转、滚轮缩放")
        hint.setObjectName("hintLabel")
        hint.setAlignment(Qt.AlignmentFlag.AlignRight)
        map_layout.addWidget(hint)
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
        _fill_window_table(self.comm_table,
                    ("序号", "开始", "结束", "时长(秒)", "最高仰角(°)", "峰值时刻"),
                    [(w.access_number, w.start_time, w.stop_time, f"{w.duration_sec:.1f}", f"{w.max_elevation_deg:.2f}", w.max_elevation_time) for w in result.windows])
        self._fill_station_table(self.p1_table, p1)
        self._fill_station_table(self.p2_table, p2)
        self._reflow_station_tables(self.station_tables.width())

        # 地图动画
        self._set_track(result)

        self.set_status(f"计算完成：两地 {len(result.windows)} 个窗口，累计 {result.total_duration_sec / 3600.0:.2f} h")

    def _fill_station_table(self, table: QTableWidget, name: str) -> None:
        if not self._last_result:
            return
        windows = self._last_result.station_windows.get(name, ())
        _fill_window_table(table,
                    ("序号", "开始", "结束", "时长(秒)", "最高仰角(°)"),
                    [(w.access_number, w.start_time, w.stop_time, f"{w.duration_sec:.1f}", f"{w.max_elevation_deg:.2f}") for w in windows])

    def _reflow_station_tables(self, width: int) -> None:
        panel_widths = []
        for group, table in zip(self.station_groups, (self.p1_table, self.p2_table)):
            header = table.horizontalHeader()
            widths = [max(header.sectionSizeHint(i), table.sizeHintForColumn(i))
                      for i in range(header.count())]
            if widths:
                metric_width = max(widths[i] for i in _WINDOW_METRIC_COLUMNS)
                for i in _WINDOW_METRIC_COLUMNS:
                    widths[i] = metric_width
            margins = group.layout().contentsMargins()
            scrollbar = table.verticalScrollBar().sizeHint().width()
            panel_widths.append(sum(widths) + margins.left() + margins.right() + 2 * table.frameWidth() + scrollbar)
        side_by_side = 2 * max(panel_widths) + self.station_layout.spacing()
        direction = (QBoxLayout.Direction.LeftToRight if width >= side_by_side
                     else QBoxLayout.Direction.TopToBottom)
        if self.station_layout.direction() != direction:
            self.station_layout.setDirection(direction)

    def eventFilter(self, watched, event):
        if watched is self.station_tables and event.type() == QEvent.Type.Resize:
            self._reflow_station_tables(event.size().width())
        return super().eventFilter(watched, event)

    # ---------------------------------------------------------------- AER 下载
    def _build_downloads(self, result: LinkVisibilityResult) -> None:
        with QSignalBlocker(self.dl_group):
            self.dl_group.clear()
            for group in build_aer_groups(result):
                self.dl_group.addItem(group.label, group)
        self._refresh_win_options()

    def _refresh_win_options(self) -> None:
        group = self.dl_group.currentData()
        with QSignalBlocker(self.dl_win):
            self.dl_win.clear()
            if group:
                for index, window in enumerate(group.windows):
                    self.dl_win.addItem(f"窗口 {window.number}", index)
                if len(group.windows) > 1:
                    numbers = " + ".join(str(window.number) for window in group.windows)
                    label = f"窗口 {numbers}" if len(group.windows) <= 3 else f"全部窗口（{len(group.windows)} 个）"
                    self.dl_win.addItem(label, -1)
        self._refresh_preview()

    def _download_selection(self):
        group = self.dl_group.currentData()
        index = self.dl_win.currentData()
        if group is None or index is None:
            return None, ()
        windows = group.windows if index == -1 else (group.windows[index],)
        return group, windows

    def _refresh_preview(self) -> None:
        group, windows = self._download_selection()
        has_data = bool(windows)
        self.dl_btn.setEnabled(has_data)
        if not has_data:
            self.dl_preview.setRowCount(0)
            self.dl_preview.setColumnCount(0)
            self.dl_info.setText("—")
            return

        rows = list(islice(chain.from_iterable(window.rows for window in windows), 500))
        total = sum(len(window.rows) for window in windows)
        self.dl_preview.setColumnCount(len(group.header))
        self.dl_preview.setHorizontalHeaderLabels(group.header)
        self.dl_preview.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for column, value in enumerate(row):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.dl_preview.setItem(row_index, column, item)
        self.dl_preview.scrollToTop()
        header = self.dl_preview.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        suffix = "（预览前 500 行）" if total > len(rows) else ""
        self.dl_info.setText(f"{group.label} · {self.dl_win.currentText()}：共 {total} 行{suffix}")

    def _export_selected(self) -> None:
        group, windows = self._download_selection()
        if not windows:
            return
        fmt = self.dl_fmt.currentData()
        label = f"AER {fmt.upper()}"
        filename = f"{group.file_stem(windows)}.{fmt}"
        path, _ = QFileDialog.getSaveFileName(self, f"导出 {label}", filename, f"{fmt.upper()} (*.{fmt})")
        if not path:
            return
        export = write_aer_csv if fmt == "csv" else write_aer_pdf
        try:
            export(path, group, windows)
        except OSError as error:
            QMessageBox.warning(self, "导出失败", str(error))
            return
        QMessageBox.information(self, "导出成功", f"{label} 已保存至：\n{path}")


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
