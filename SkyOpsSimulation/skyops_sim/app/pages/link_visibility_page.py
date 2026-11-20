"""星地建链可见性、AER 导出和轨迹播放页面。"""

from __future__ import annotations

from bisect import bisect_right
import copy
from datetime import datetime, timezone
from functools import lru_cache
from itertools import chain, islice
from math import isclose, isfinite
from pathlib import Path
from zoneinfo import ZoneInfo

from PySide6.QtCore import QDate, QDateTime, QElapsedTimer, QEvent, QPointF, QSignalBlocker, QTime, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QBoxLayout,
    QComboBox,
    QDateTimeEdit,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from skyops_sim.app.aer_export import build_aer_groups, write_aer_csv, write_aer_pdf
from skyops_sim.app.icons import action_button, apply_icon
from skyops_sim.app.widgets.coordinate_input import CoordinateInput
from skyops_sim.app.widgets.engine_selection import EngineSelection
from skyops_sim.app.widgets.orbit_globe import (
    OrbitGlobeWidget, SATELLITE_COLOR, SPACE_COLOR, STATION_COLORS, world_rings,
)
from skyops_sim.app.widgets.side_navigation import SideNavigation
from skyops_sim.simulations.common import SatelliteConfig, parse_stk_time
from skyops_sim.simulations.global_coverage.presets import station_template
from skyops_sim.simulations.link_visibility.config import (
    LinkStationConfig,
    LinkVisibilityConfig,
    LinkVisibilityResult,
)

_BEIJING = ZoneInfo("Asia/Shanghai")


@lru_cache(maxsize=1)
def _coastline_path() -> QPainterPath:
    outline = QPainterPath()
    for ring in world_rings():
        lon, lat = ring[0]
        outline.moveTo(lon, -lat)
        for lon, lat in ring[1:]:
            outline.lineTo(lon, -lat)
    return outline


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
        self._track_path = QPainterPath()
        self._zoom = 1.0
        self._offset = QPointF()
        self._drag_pos: QPointF | None = None

    def reset_view(self) -> None:
        self._zoom = 1.0
        self._offset = QPointF()
        self._update_view()

    def zoom_by(self, factor: float, anchor: QPointF | None = None) -> None:
        center = self._center()
        if anchor is None:
            anchor = center
        zoom = min(8.0, max(1.0, self._zoom * factor))
        self._offset = anchor - center - (anchor - center - self._offset) * (zoom / self._zoom)
        self._zoom = zoom
        self._update_view()

    def _center(self) -> QPointF:
        return QPointF(self.width() / 2.0, self.height() / 2.0)

    def _map_height(self) -> float:
        return min(float(self.height()), self.width() / 2.0)

    def _update_view(self) -> None:
        height = self._map_height() * self._zoom
        limit_x = max(0.0, height - self.width() / 2.0)
        limit_y = max(0.0, (height - self.height()) / 2.0)
        self._offset = QPointF(
            min(limit_x, max(-limit_x, self._offset.x())),
            min(limit_y, max(-limit_y, self._offset.y())),
        )
        if self._drag_pos is not None:
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        elif self._zoom > 1.0:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            self.unsetCursor()
        self._cache_key = None
        self.update()

    def wheelEvent(self, event) -> None:
        delta = event.angleDelta().y() or event.pixelDelta().y()
        if delta:
            self.zoom_by(1.25 ** (delta / 120.0), event.position())
            event.accept()
        else:
            super().wheelEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._zoom > 1:
            self._drag_pos = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_pos is not None:
            self._offset += event.position() - self._drag_pos
            self._drag_pos = event.position()
            self._update_view()
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._drag_pos is not None:
            self._drag_pos = None
            self._update_view()
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def resizeEvent(self, event) -> None:
        self._update_view()
        super().resizeEvent(event)

    def set_data(self, track, stations) -> None:
        self._track = track
        self._stations = tuple(stations[:2])
        self._position = 0.0
        self._track_path = QPainterPath()
        previous = None
        for point in track:
            lon, lat = point.longitude_deg, point.latitude_deg
            if not (isfinite(lon) and isfinite(lat)):
                previous = None
                continue
            if previous is None or abs(lon - previous) > 180:
                self._track_path.moveTo(lon, -lat)
            else:
                self._track_path.lineTo(lon, -lat)
            previous = lon
        self._cache_key = None
        self.update()

    def set_position(self, position: float) -> None:
        self._position = position
        self.update()

    def _project(self, lon: float, lat: float) -> QPointF:
        # 锁定 2:1（360°×180°）等距圆柱投影，避免窗口过宽时把地球横向拉扁
        pixels_per_degree = self._map_height() * self._zoom / 180.0
        return self._center() + self._offset + QPointF(lon, -lat) * pixels_per_degree

    def _make_background(self, scale: float) -> QPixmap:
        image = QPixmap(round(self.width() * scale), round(self.height() * scale))
        image.setDevicePixelRatio(scale)
        image.fill(QColor(SPACE_COLOR))
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.save()
        painter.translate(self._center() + self._offset)
        pixels_per_degree = self._map_height() * self._zoom / 180.0
        painter.scale(pixels_per_degree, pixels_per_degree)
        for path, color, thickness in (
            (_coastline_path(), QColor("#324963"), 0.7),
            (self._track_path, QColor(34, 211, 238), 1.6),
        ):
            pen = QPen(color, thickness * scale)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.drawPath(path)
        painter.restore()

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
    visible_rows = max(1, min(6, len(rows)))
    table.setFixedHeight(
        header.height() + visible_rows * table.verticalHeader().defaultSectionSize()
        + table.horizontalScrollBar().sizeHint().height() + 2 * table.frameWidth()
    )


class LinkVisibilityPage(QWidget):
    run_requested = Signal(object, str)
    stk_file_requested = Signal(str, str, str)

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
        title = QLabel("站点与时段")
        title.setObjectName("toolHeading")
        self.satellite_summary = QLabel()
        self.satellite_summary.setObjectName("hintLabel")
        heading = QHBoxLayout()
        heading.addWidget(title)
        heading.addStretch(1)
        heading.addWidget(self.satellite_summary)
        parameters.addLayout(heading)
        parameters.addWidget(self._build_time_card())
        loc_row = QHBoxLayout()
        loc_row.addWidget(self._build_loc_card(0))
        loc_row.addWidget(self._build_loc_card(1))
        parameters.addLayout(loc_row)
        parameters.addWidget(self._build_compute_bar())
        parameters.addStretch(1)
        self.sections.addWidget(self._scroll(settings))

        results = QWidget()
        root = QVBoxLayout(results)
        result_heading = QHBoxLayout()
        result_title = QLabel("窗口与下载")
        result_title.setObjectName("toolHeading")
        result_heading.addWidget(result_title)
        result_heading.addStretch(1)
        self.result_engine = QLabel()
        self.result_engine.setObjectName("hintLabel")
        result_heading.addWidget(self.result_engine)
        self.stk_actions = action_button("更多", "chevron-down")
        menu = QMenu(self.stk_actions)
        menu.addAction("保存 STK 场景…", lambda: self._request_stk_file("save"))
        menu.addAction("导出卫星星历…", lambda: self._request_stk_file("ephemeris"))
        self.stk_actions.setMenu(menu)
        self.stk_actions.hide()
        result_heading.addWidget(self.stk_actions)
        root.addLayout(result_heading)
        self.run_context = QLabel()
        self.run_context.setObjectName("hintLabel")
        self.run_context.setWordWrap(True)
        self.run_context.hide()
        root.addWidget(self.run_context)

        self.result_summary = QLabel("计算完成后显示窗口和累计通信时长。")
        self.result_summary.setObjectName("linkSummary")
        root.addWidget(self.result_summary)

        # 窗口表
        self.comm_table = QTableWidget()
        root.addWidget(self._section("两地通信窗口（北京时间）", self.comm_table))
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
        self.station_tables.hide()

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
        dl_row.addStretch(1)
        track_button = action_button("查看轨迹", "globe")
        track_button.clicked.connect(lambda: self.sections.setCurrentIndex(2))
        dl_row.addWidget(track_button)
        dl_layout.addLayout(dl_row)
        preview_row = QHBoxLayout()
        preview_button = action_button("预览 AER 数据", "layers")
        preview_button.setCheckable(True)
        preview_row.addWidget(preview_button)
        self.dl_info = QLabel("—")
        self.dl_info.setObjectName("hintLabel")
        preview_row.addWidget(self.dl_info, 1)
        dl_layout.addLayout(preview_row)
        self.dl_preview = QTableWidget()
        self.dl_preview.setMaximumHeight(280)
        self.dl_preview.hide()
        preview_button.toggled.connect(self.dl_preview.setVisible)
        dl_layout.addWidget(self.dl_preview)
        root.addWidget(dl_card)
        stations_toggle = action_button("单站可用窗口", "chevron-down")
        stations_toggle.setCheckable(True)
        stations_toggle.toggled.connect(self.station_tables.setVisible)
        root.addWidget(stations_toggle, alignment=Qt.AlignmentFlag.AlignLeft)
        root.addWidget(self.station_tables)

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
        heading = QLabel("轨迹地图")
        heading.setObjectName("toolHeading")
        map_layout.addWidget(heading)
        self.map_widget = WorldMapWidget()
        self.globe_widget = OrbitGlobeWidget()
        views = QHBoxLayout()
        views.setSpacing(12)
        map_header = QHBoxLayout()
        map_header.addWidget(QLabel("二维星下点"))
        map_header.addStretch(1)
        for text, tooltip, factor in (("−", "缩小二维地图", 0.8), ("+", "放大二维地图", 1.25)):
            button = QPushButton(text)
            button.setToolTip(tooltip)
            button.setAccessibleName(tooltip)
            button.clicked.connect(lambda _, factor=factor: self.map_widget.zoom_by(factor))
            map_header.addWidget(button)
        full_map = QPushButton("全图")
        full_map.setToolTip("恢复二维地图的默认视角")
        full_map.clicked.connect(self.map_widget.reset_view)
        map_header.addWidget(full_map)
        map_header_widget = QWidget()
        map_header.setContentsMargins(0, 0, 0, 0)
        map_header_widget.setLayout(map_header)
        ground_map = QGroupBox()
        ground_layout = QVBoxLayout(ground_map)
        ground_layout.addWidget(map_header_widget)
        ground_layout.addWidget(self.map_widget, 1)
        orbit = QGroupBox()
        orbit_layout = QVBoxLayout(orbit)
        orbit_title = QLabel("三维轨道")
        orbit_title.setToolTip("光束表示当前时刻可见的卫星至地面站链路。")
        orbit_title.setMinimumHeight(full_map.sizeHint().height())
        orbit_layout.addWidget(orbit_title)
        orbit_layout.addWidget(self.globe_widget, 1)
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
        hint = QLabel("二维：滚轮缩放、拖动平移      三维：滚轮缩放、拖动旋转")
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
        form = QGridLayout(card)
        form.setColumnStretch(0, 1)
        form.setColumnStretch(1, 1)

        preset_combo = QComboBox()
        preset_combo.addItem("自定义")
        presets = {station.name: station for station in station_template("domestic")}
        for key, label in (("LinGang", "上海临港站"), ("KaShi", "喀什站")):
            preset_combo.addItem(label, presets[key])
        form.addWidget(self._field("地面站预设", preset_combo), 0, 0)

        name_edit = QLineEdit(st.name)
        form.addWidget(self._field("站点名称", name_edit), 1, 0, 1, 2)

        mode_combo = QComboBox()
        mode_combo.addItem("十进制", "decimal")
        mode_combo.addItem("度分秒", "dms")
        form.addWidget(self._field("坐标格式", mode_combo), 0, 1)

        latitude = CoordinateInput(True, st.latitude_deg)
        longitude = CoordinateInput(False, st.longitude_deg)
        coordinates = QWidget()
        rows = QFormLayout(coordinates)
        rows.setContentsMargins(0, 0, 0, 0)
        rows.addRow("纬度", latitude)
        rows.addRow("经度", longitude)
        form.addWidget(coordinates, 2, 0, 1, 2)

        def update_format() -> None:
            dms = mode_combo.currentData() == "dms"
            latitude.set_dms(dms)
            longitude.set_dms(dms)

        mode_combo.currentIndexChanged.connect(update_format)

        custom = st.name, st.latitude_deg, st.longitude_deg

        def apply_preset() -> None:
            nonlocal custom
            preset = preset_combo.currentData()
            if preset is not None:
                if not name_edit.isReadOnly():
                    custom = name_edit.text(), latitude.value(), longitude.value()
                values = preset_combo.currentText(), preset.lat, preset.lon
            else:
                values = custom
            name, lat, lon = values
            name_edit.setText(name)
            name_edit.setReadOnly(preset is not None)
            coordinates.setEnabled(preset is None)
            latitude.set_value(lat)
            longitude.set_value(lon)

        preset_combo.currentIndexChanged.connect(apply_preset)
        for i in range(1, preset_combo.count()):
            preset = preset_combo.itemData(i)
            if (
                st.name == preset_combo.itemText(i)
                and isclose(st.latitude_deg, preset.lat, abs_tol=5e-7)
                and isclose(st.longitude_deg, preset.lon, abs_tol=5e-7)
            ):
                preset_combo.setCurrentIndex(i)
                break

        min_el = _spin(0.0, 90.0, st.min_elevation_deg, 2)
        gso = _spin(0.0, 180.0, st.gso_avoid_deg, 2)
        form.addWidget(self._field("最低仰角（°）", min_el), 3, 0)
        form.addWidget(self._field("GSO 隔离角（°）", gso), 3, 1)

        setattr(self, f"_loc{index}", {
            "name": name_edit, "preset": preset_combo, "mode": mode_combo,
            "latitude": latitude, "longitude": longitude,
            "min_el": min_el, "gso": gso,
        })
        return card

    @staticmethod
    def _field(title: str, field: QWidget) -> QWidget:
        widget = QWidget()
        column = QVBoxLayout(widget)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(4)
        label = QLabel(title)
        label.setObjectName("fieldCaption")
        label.setBuddy(field)
        column.addWidget(label)
        column.addWidget(field)
        return widget

    def _build_time_card(self) -> QWidget:
        card = QGroupBox("计算时段（北京时间）")
        layout = QHBoxLayout(card)
        self.start_edit = self._time_edit(self._config.scenario.start_time)
        self.stop_edit = self._time_edit(self._config.scenario.stop_time)
        layout.addWidget(self._field("开始时间", self.start_edit), 1)
        layout.addWidget(self._field("结束时间", self.stop_edit), 1)
        return card

    @staticmethod
    def _time_edit(utc_text: str) -> QDateTimeEdit:
        local = parse_stk_time(utc_text).astimezone(_BEIJING)
        # Store the displayed wall-clock fields in UTC to avoid the PC's time zone.
        widget = QDateTimeEdit()
        widget.setTimeSpec(Qt.TimeSpec.UTC)
        date = QDate(local.year, local.month, local.day)
        time = QTime(local.hour, local.minute, local.second)
        widget.setDateTime(QDateTime(date, time, Qt.TimeSpec.UTC))
        widget.setCalendarPopup(True)
        widget.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        return widget

    def _build_compute_bar(self) -> QWidget:
        card = QWidget()
        layout = QHBoxLayout(card)
        layout.setContentsMargins(0, 7, 0, 0)
        self.engine_selection = EngineSelection(self._config.stk)
        layout.addWidget(self.engine_selection)
        self.run_btn = action_button("计算建链", "play", primary=True)
        self.run_btn.clicked.connect(lambda: self._emit_run())
        layout.addStretch(1)
        layout.addWidget(self.run_btn)
        return card

    # ---------------------------------------------------------------- 动作
    def set_reference_satellite(self, profile) -> None:
        self._config.satellite = SatelliteConfig.from_reference(profile, self._config.satellite.step)
        self._config.tle_file = ""
        self.satellite_summary.setText(profile.label)

    def _read_loc(self, index: int) -> LinkStationConfig:
        loc = getattr(self, f"_loc{index}")
        st = self._config.stations[index]
        preset = loc["preset"].currentData()
        return LinkStationConfig(
            name=loc["name"].text().strip() or st.name,
            latitude_deg=preset.lat if preset else loc["latitude"].value(),
            longitude_deg=preset.lon if preset else loc["longitude"].value(),
            altitude_m=st.altitude_m,
            min_elevation_deg=loc["min_el"].value(),
            gso_avoid_deg=loc["gso"].value(),
        )

    def _emit_run(self) -> None:
        cfg = copy.deepcopy(self._config)
        cfg.stations[0] = self._read_loc(0)
        cfg.stations[1] = self._read_loc(1)
        if cfg.stations[0].name.casefold() == cfg.stations[1].name.casefold():
            QMessageBox.warning(self, "请检查站点", "两个地面站须使用不同的名称。")
            return
        start, stop = (
            field.dateTime().toPython().replace(tzinfo=_BEIJING).astimezone(timezone.utc)
            for field in (self.start_edit, self.stop_edit)
        )
        if not 0 < (stop - start).total_seconds() <= 8 * 86400:
            QMessageBox.warning(self, "请检查计算时段", "结束时间须晚于开始时间，且计算时段最多为 8 天。")
            return
        cfg.scenario.start_time = start.strftime("%Y-%m-%d %H:%M:%S")
        cfg.scenario.stop_time = stop.strftime("%Y-%m-%d %H:%M:%S")
        cfg.stk = self.engine_selection.config()
        cfg.dual_station_sync = True
        self.status_label.setText("正在计算...")
        self.run_requested.emit(cfg, "normal")

    def _request_stk_file(self, action: str) -> None:
        result = self._last_result
        if result is None or not result.stk_scenario:
            return
        ephemeris = action == "ephemeris"
        suffix = ".e" if ephemeris else ".sc"
        title = "导出 STK 星历" if ephemeris else "保存 STK 场景"
        stem = result.satellite_name if ephemeris else result.stk_scenario
        filename, _ = QFileDialog.getSaveFileName(self, title, stem + suffix, f"STK 文件 (*{suffix})")
        if not filename:
            return
        path = Path(filename)
        if path.suffix.lower() != suffix:
            path = Path(str(path) + suffix)
        self.set_status(f"正在{title}…")
        self.stk_file_requested.emit(action, str(path), result.stk_scenario)

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
        pt = self._last_result.ground_track[index]
        self.map_widget.set_position(position)
        self.globe_widget.set_position(position, (pt.linked1, pt.linked2))
        with QSignalBlocker(self.slider):
            self.slider.setValue(index)
        status = "两地通信中" if pt.linked else "单站可见" if pt.linked1 or pt.linked2 else "未建链"
        self.map_status.setText(f"{pt.time}　{status}")

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
        self.engine_selection.setEnabled(not busy)
        self.stk_actions.setEnabled(not busy)

    def set_status(self, text: str) -> None:
        self.status_label.setText(text)
        self.status_label.setToolTip(text)

    def show_result(self, result: LinkVisibilityResult) -> None:
        self._last_result = result
        engine_label = {"python": "Python", "stk": "STK 12", "compare": "Python / STK 12"}
        self.result_engine.setText(f"计算引擎 · {engine_label[result.engine_used]}")
        self.stk_actions.setVisible(bool(result.stk_scenario))
        self.run_context.setText(f"卫星 {result.satellite_name} · {result.start_time} 至 {result.stop_time}")
        self.run_context.show()
        self.sections.setCurrentIndex(1)
        self._build_downloads(result)

        self.result_summary.setText(
            f"两地通信窗口 <b>{len(result.windows)} 个</b>　　"
            f"累计通信时长 <b>{result.total_duration_sec / 3600.0:.2f} h</b>"
        )
        p1, p2 = result.station_names[0], result.station_names[1] if len(result.station_names) > 1 else ""
        for group, name in zip(self.station_groups, (p1, p2)):
            group.setVisible(bool(name))
            if name:
                group.setTitle(f"{name} · 累计 {result.station_totals.get(name, 0.0) / 3600.0:.2f} h")

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


