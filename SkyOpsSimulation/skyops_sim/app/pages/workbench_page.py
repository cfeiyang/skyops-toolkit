"""Surface common STK 12 operations as forms and direct actions."""

from functools import partial
from pathlib import Path

from PySide6.QtCore import QDateTime, QThread, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QDateTimeEdit, QDoubleSpinBox,
    QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPlainTextEdit, QScrollArea, QVBoxLayout, QWidget,
)

from skyops_sim.app.icons import action_button, apply_icon
from skyops_sim.app.widgets.side_navigation import SectionStack, SideNavigation
from skyops_sim.infrastructure.paths import application_root
from skyops_sim.infrastructure.reference_satellite import ReferenceSatellite
from skyops_sim.stk import workbench_commands as commands
from skyops_sim.stk.desktop_bridge import invoke


STEPS = (
    ("场景", "calendar-range"),
    ("地面站", "radio-tower"),
    ("可见性计算", "clock-3"),
)


def dropdown(*choices):
    widget = QComboBox()
    for text, value in choices:
        widget.addItem(text, value)
    return widget


def decimal(value, low, high, places=3):
    widget = QDoubleSpinBox()
    widget.setDecimals(places)
    widget.setRange(low, high)
    widget.setValue(value)
    widget.setKeyboardTracking(False)
    return widget


def date_field(value):
    widget = QDateTimeEdit(value)
    widget.setTimeSpec(Qt.TimeSpec.UTC)
    widget.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
    widget.setCalendarPopup(True)
    return widget


def fields(*entries):
    """Arrange labeled fields two to a row, with optional full width rows."""
    container = QWidget()
    grid = QGridLayout(container)
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setHorizontalSpacing(14)
    grid.setVerticalSpacing(13)
    row = column = 0
    for title, control, span in entries:
        if span == 2 and column:
            row += 1
            column = 0
        label = QLabel(title)
        label.setObjectName("fieldCaption")
        label.setBuddy(control)
        item = QVBoxLayout()
        item.setSpacing(4)
        item.addWidget(label)
        item.addWidget(control)
        grid.addLayout(item, row, column, 1, span)
        column += span
        if column == 2:
            column = 0
            row += 1
    grid.setColumnStretch(0, 1)
    grid.setColumnStretch(1, 1)
    return container


def prepare_reference_orbit(profile: ReferenceSatellite, create: bool):
    tle = profile.load_tle(application_root() / "data")
    return commands.satellite(profile.name, "tle", create, tle1=tle.line1, tle2=tle.line2)


class DesktopTask(QThread):
    reply = Signal(dict)

    def __init__(self, action, plan, scenario, parent):
        super().__init__(parent)
        self.action = action
        self.plan = plan
        self.scenario = scenario

    def run(self):
        try:
            plan = self.plan() if callable(self.plan) else self.plan
            self.reply.emit(invoke(self.action, plan, self.scenario))
        except Exception as error:
            self.reply.emit({"error": str(error)})


class WorkbenchPage(QWidget):
    busy_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._task = None
        self._simulation_busy = False
        self._connected = False
        self._scenario = ""

        self._error_detail = ""
        self._selections = []
        self._reference_satellite = ReferenceSatellite()
        self._build_connection()
        self._build_forms()

    @property
    def is_busy(self):
        return self._task is not None

    def _build_connection(self):
        self.connection_controls = QWidget()
        controls = QHBoxLayout(self.connection_controls)
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(8)
        self.connection = QLabel("STK 12 未连接")
        self.connection.setObjectName("connectionStatus")
        self.connection.setTextFormat(Qt.TextFormat.PlainText)
        controls.addWidget(self.connection)
        self.connect_button = action_button("连接 STK", "plug")
        self.connect_button.setToolTip("先打开本机 STK 12，再连接已打开的实例。")
        self.connect_button.clicked.connect(self.connect_stk)
        controls.addWidget(self.connect_button)

    def _build_forms(self):
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(14)

        self.forms = SectionStack()

        panel = QFrame()
        panel.setObjectName("workbenchPanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)

        panel_layout.addWidget(self.forms)

        footer = QFrame()
        footer.setObjectName("workbenchFooter")
        actions = QHBoxLayout(footer)
        actions.setContentsMargins(17, 10, 17, 10)
        self.status = QLabel()
        self.status.setObjectName("workbenchStatus")
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        actions.addWidget(self.status, 1)
        self.details = action_button("详情", "layers")
        self.details.hide()
        self.details.clicked.connect(self._show_detail)
        actions.addWidget(self.details)
        self.save = action_button("保存场景", "save")
        self.save.clicked.connect(self._save_scene)
        actions.addWidget(self.save)
        self.action = action_button("新建场景", "plus", primary=True)
        self.action.clicked.connect(self._apply)
        actions.addWidget(self.action)
        panel_layout.addWidget(footer)
        scroll = QScrollArea()
        scroll.setObjectName("workbenchScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        column = QWidget()
        column.setObjectName("workbenchBody")
        column_layout = QVBoxLayout(column)
        column_layout.setContentsMargins(0, 0, 0, 0)
        column_layout.addWidget(panel)
        column_layout.addStretch(1)
        scroll.setWidget(column)
        for builder in (self._object_form, self._station_form, self._access_form):
            self.forms.addWidget(builder())
        outer.addWidget(SideNavigation(STEPS, self.forms))
        outer.addWidget(scroll, 1)
        self.forms.currentChanged.connect(self._refresh_actions)
        self.object_forms.currentChanged.connect(self._refresh_actions)
        self._refresh_actions()

    @staticmethod
    def _form(heading):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(19, 17, 19, 18)
        layout.setSpacing(13)
        title = QLabel(heading)
        title.setObjectName("toolHeading")
        layout.addWidget(title)
        return page, layout

    @staticmethod
    def _add_fields(layout, container):
        container.setMaximumWidth(790)
        layout.addWidget(container)

    def _selection(self, kind):
        widget = QComboBox()
        widget.setPlaceholderText("请选择")
        self._selections.append((widget, kind))
        return widget

    def _file_input(self, edit, filters, export=False):
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(edit, 1)
        browse = action_button("浏览", "folder-open")
        browse.clicked.connect(lambda: self._browse(edit, filters, export))
        layout.addWidget(browse)
        return row

    def _browse(self, edit, filters, export):
        if not export:
            file, _ = QFileDialog.getOpenFileName(self, "选择文件", edit.text(), filters)
        else:
            file, kind = QFileDialog.getSaveFileName(self, "选择星历导出位置", edit.text(), filters)
            if file and not Path(file).suffix:
                file += ".oem" if "*.oem" in kind else ".e"
        if file:
            edit.setText(str(Path(file)))

    def _object_form(self):
        page, layout = self._form("场景")
        self.object_type = dropdown(("场景", "scenario"), ("卫星", "satellite"))
        self._add_fields(layout, fields(("操作对象", self.object_type, 1)))
        self.object_forms = SectionStack()
        self.object_forms.addWidget(self._scene_form())
        self.object_forms.addWidget(self._satellite_form())
        layout.addWidget(self.object_forms, 1)
        self.object_type.currentIndexChanged.connect(self.object_forms.setCurrentIndex)
        return page

    @staticmethod
    def _object_fields():
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(13)
        return page, layout

    def _scene_form(self):
        page, layout = self._object_fields()
        self.scene_mode = dropdown(("新建场景", "new"), ("打开已有场景", "open"))
        self.scene_name = QLineEdit("GroundPass")
        start = QDateTime.currentDateTimeUtc()
        self.scene_start = date_field(start)
        self.scene_stop = date_field(start.addDays(1))
        self.scene_file = QLineEdit()
        self._add_fields(layout, fields(("操作", self.scene_mode, 1)))
        self.new_scene_fields = fields(
            ("场景名", self.scene_name, 2),
            ("开始时间（UTC）", self.scene_start, 1),
            ("结束时间（UTC）", self.scene_stop, 1),
        )
        self.open_scene_fields = fields(
            ("场景文件", self._file_input(self.scene_file, "STK 场景 (*.sc *.vdf)"), 2),
        )
        self._add_fields(layout, self.new_scene_fields)
        self._add_fields(layout, self.open_scene_fields)
        self.open_scene_fields.hide()
        self.scene_mode.currentIndexChanged.connect(self._update_scene_fields)
        layout.addStretch(1)
        return page

    def _satellite_form(self):
        page, layout = self._object_fields()
        self.sat_mode = dropdown(("创建卫星", "new"), ("更新卫星", "edit"), ("导出星历", "export"))
        self.sat_name = QLineEdit("Satellite1")
        self.sat_existing = self._selection("satellites")
        self.source = dropdown(("使用右上角卫星设置", "reference"), ("经典轨道根数", "classical"),
                               ("导入星历文件", "ephemeris"), ("两行 TLE", "tle"))
        self._add_fields(layout, fields(("操作", self.sat_mode, 1)))
        self.sat_name_fields = fields(("卫星名", self.sat_name, 2))
        self.sat_existing_fields = fields(("卫星", self.sat_existing, 2))
        self.source_fields = fields(("轨道来源", self.source, 1))
        for widget in (self.sat_name_fields, self.sat_existing_fields, self.source_fields):
            self._add_fields(layout, widget)

        self.propagator = dropdown(*((value, value) for value in commands.PROPAGATORS))
        self.orbit_frame = dropdown(*((value, value) for value in commands.FRAMES))
        self.axis = decimal(6878.137, 6378.138, 1000000)
        self.ecc = decimal(0.001, 0, 0.99999999, 8)
        self.inc = decimal(51.6, 0, 180, 6)
        self.arg = decimal(0, -360, 360, 6)
        self.raan = decimal(0, -360, 360, 6)
        self.mean = decimal(0, -360, 360, 6)
        self.step = decimal(60, 0.001, 86400)
        self.ephemeris = QLineEdit()
        self.export_path = QLineEdit()
        self.tle = QPlainTextEdit()
        self.tle.setPlaceholderText("粘贴两行 TLE，保留行内空格")
        self.tle.setFixedHeight(72)
        self.reference_source_label = QLabel(self._reference_satellite.label)
        self.reference_source_label.setObjectName("hintLabel")
        self.orbit_fields = {
            "reference": fields(("公共卫星", self.reference_source_label, 2)),
            "classical": fields(
                ("半长轴（km）", self.axis, 1), ("倾角（°）", self.inc, 1),
                ("偏心率", self.ecc, 1), ("参考系", self.orbit_frame, 1),
                ("近地点幅角（°）", self.arg, 1), ("升交点赤经（°）", self.raan, 1),
                ("平近点角（°）", self.mean, 1), ("传播步长（秒）", self.step, 1),
                ("传播器", self.propagator, 1),
            ),
            "ephemeris": fields(("星历文件", self._file_input(self.ephemeris, "星历 (*.e *.be *.oem)"), 2)),
            "tle": fields(("两行 TLE", self.tle, 2)),
            "export": fields(("导出路径", self._file_input(
                self.export_path, "STK 星历 (*.e);;CCSDS OEM (*.oem)", export=True), 2)),
        }
        for key, form in self.orbit_fields.items():
            self._add_fields(layout, form)
            form.setVisible(key == "reference")
        self.sat_name_fields.hide()
        self.sat_existing_fields.hide()
        self.sat_mode.currentIndexChanged.connect(self._update_sat_fields)
        self.source.currentIndexChanged.connect(self._update_sat_fields)
        layout.addStretch(1)
        return page

    def _station_form(self):
        page, layout = self._form("地面站")
        self.site_mode = dropdown(("添加地面站", "new"), ("更新已有地面站", "edit"))
        self.site_name = QLineEdit("Station1")
        self.site_existing = self._selection("stations")
        self.lat = decimal(31.2304, -90, 90, 6)
        self.lon = decimal(121.4737, -180, 180, 6)
        self.site_gso = decimal(15, 0, 180)
        self.site_elevation = decimal(10, -90, 90)
        self.site_name_fields = fields(("地面站名", self.site_name, 2))
        self.site_existing_fields = fields(("地面站", self.site_existing, 2))
        self._add_fields(layout, fields(("操作", self.site_mode, 1)))
        self._add_fields(layout, self.site_name_fields)
        self._add_fields(layout, self.site_existing_fields)
        self._add_fields(layout, fields(
            ("纬度（°）", self.lat, 1), ("经度（°）", self.lon, 1),
            ("GSO 隔离角（°）", self.site_gso, 1), ("最低仰角（°）", self.site_elevation, 1),
        ))
        self.site_existing_fields.hide()
        self.site_mode.currentIndexChanged.connect(self._update_site_fields)
        layout.addStretch(1)
        return page

    def _access_form(self):
        page, layout = self._form("可见性计算")
        self.access_site = self._selection("stations")
        self.access_sat = self._selection("satellites")
        self._add_fields(layout, fields(("地面站", self.access_site, 1),
                                        ("目标卫星", self.access_sat, 1)))
        hint = QLabel("按当前场景时段计算，在 STK 的时间线中查看可见窗口。")
        hint.setObjectName("hintLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch(1)
        return page


    def _update_scene_fields(self):
        is_new = self.scene_mode.currentData() == "new"
        self.new_scene_fields.setVisible(is_new)
        self.open_scene_fields.setVisible(not is_new)
        self._refresh_actions()

    def _update_sat_fields(self):
        mode = self.sat_mode.currentData()
        source = "export" if mode == "export" else self.source.currentData()
        self.sat_name_fields.setVisible(mode == "new" and source != "reference")
        self.sat_existing_fields.setVisible(mode != "new")
        self.source_fields.setVisible(mode != "export")
        for key, form in self.orbit_fields.items():
            form.setVisible(key == source)
        self._refresh_actions()

    def _update_site_fields(self):
        is_new = self.site_mode.currentData() == "new"
        self.site_name_fields.setVisible(is_new)
        self.site_existing_fields.setVisible(not is_new)
        self._refresh_actions()

    def set_simulation_busy(self, busy):
        self._simulation_busy = busy
        self._refresh_actions()

    def set_reference_satellite(self, profile: ReferenceSatellite) -> None:
        self._reference_satellite = profile
        self.reference_source_label.setText(profile.label)

    def _operation_index(self):
        section = self.forms.currentIndex()
        if section < 0:
            return section
        return self.object_forms.currentIndex() if section == 0 else section + 1

    def _refresh_actions(self):
        index = self._operation_index()
        if index < 0:
            return
        self.forms.updateGeometry()
        captions = (
            ("新建场景", "plus") if self.scene_mode.currentData() == "new" else ("打开场景", "folder-open"),
            {"new": ("创建卫星", "plus"), "edit": ("更新卫星", "pencil"),
             "export": ("导出星历", "download")}[self.sat_mode.currentData()],
            ("添加地面站", "plus") if self.site_mode.currentData() == "new" else ("更新地面站", "pencil"),
            ("计算可见时段", "play"),
        )
        text, artwork = captions[index]
        self.action.setText(text)
        apply_icon(self.action, artwork, primary=True)
        available = not self.is_busy and not self._simulation_busy
        self.connect_button.setEnabled(available)
        self.save.setVisible(index == 0)
        self.save.setEnabled(available and self._connected and bool(self._scenario))
        self.action.setEnabled(available and self._connected and (index == 0 or bool(self._scenario)))

    def connect_stk(self):
        self._start("attach", None, "已连接 STK 12。")

    def _save_scene(self):
        self._start("run", commands.save_scenario(), "已保存当前场景。")

    @staticmethod
    def _selected(widget, label):
        if not widget.currentText().strip():
            raise ValueError(f"请选择{label}。")
        return widget.currentText()

    def _plan_current(self):
        page = self._operation_index()
        if page == 0:
            if self.scene_mode.currentData() == "open":
                return commands.open_scenario(self.scene_file.text()), "已打开场景。"
            return commands.scenario(
                self.scene_name.text(), self.scene_start.dateTime().toPython(),
                self.scene_stop.dateTime().toPython(),
            ), "已新建场景。"
        if page == 1:
            mode = self.sat_mode.currentData()
            sat = self.sat_name.text() if mode == "new" else self._selected(self.sat_existing, "卫星")
            if mode == "export":
                return commands.export_ephemeris(sat, self.export_path.text()), "已导出星历。"
            source = self.source.currentData()
            if source == "reference":
                profile = self._reference_satellite
                if mode == "edit" and sat.casefold() != profile.name.casefold():
                    raise ValueError(f"请选择公共卫星 {profile.name}，或切换轨道来源。")
                return partial(prepare_reference_orbit, profile, mode == "new"), "已应用公共卫星轨道。"
            tle = self.tle.toPlainText().strip().splitlines() if source == "tle" else []
            if source == "tle" and len(tle) != 2:
                raise ValueError("请输入同一颗卫星的两行 TLE。")
            return commands.satellite(
                sat, source, mode == "new", propagator=self.propagator.currentData(),
                frame=self.orbit_frame.currentData(), step=self.step.value(),
                a_km=self.axis.value(), e=self.ecc.value(), inc=self.inc.value(),
                arg=self.arg.value(), raan=self.raan.value(), mean=self.mean.value(),
                file=self.ephemeris.text(), tle1=tle[0] if tle else "", tle2=tle[1] if tle else "",
            ), "已保存卫星轨道。"
        if page == 2:
            create = self.site_mode.currentData() == "new"
            station = self.site_name.text() if create else self._selected(self.site_existing, "地面站")
            return commands.station(
                station, self.lat.value(), self.lon.value(), create,
                elevation=self.site_elevation.value(), gso=self.site_gso.value(),
            ), "已保存地面站位置和角度约束。"
        return commands.access(self._selected(self.access_sat, "卫星"),
                               self._selected(self.access_site, "地面站")), "已计算可见时段，请在 STK 查看。"

    def _apply(self):
        try:
            plan, message = self._plan_current()
        except ValueError as error:
            self._set_status(str(error), problem=True)
            return
        self._start("run", plan, message)

    def _start(self, action, plan, success):
        if self.is_busy or self._simulation_busy or (plan is not None and not self._connected):
            return
        needs_scenario = callable(plan) or (plan is not None and plan.requires_scenario)
        expected = self._scenario if needs_scenario else ""
        self._task = DesktopTask(action, plan, expected, self)
        self._task.reply.connect(self._receive)
        self._task.finished.connect(self._finished)
        self._success = success
        self._set_status("正在连接 STK…" if action == "attach" else "正在处理…")
        self._refresh_actions()
        self.busy_changed.emit(True)
        self._task.start()

    def _set_status(self, message, detail="", *, problem=False):

        self._error_detail = detail
        self.status.setText(message)
        self.status.setProperty("problem", problem or bool(detail))
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        self.details.setVisible(bool(detail))

    def _show_detail(self):
        dialog = QMessageBox(QMessageBox.Icon.Warning, "STK 操作详情",
                             self._error_detail, parent=self)
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.exec()

    def _receive(self, reply):
        if "version" in reply:
            version = reply["version"]
            self._connected = bool(version)
            self._scenario = reply.get("scenario", "")
            badge = "STK 12 · " + (self._scenario or "已连接") if version else "STK 12 未连接"
            self.connection.setText(badge)
            self.connection.setToolTip(str(version))
            self.connection.setProperty("connected", self._connected)
            self.connection.style().unpolish(self.connection)
            self.connection.style().polish(self.connection)
            for box, kind in self._selections:
                previous = box.currentText()
                names = sorted(reply.get(kind, []), key=str.casefold)
                box.clear()
                box.addItems(names)
                if previous in names:
                    box.setCurrentText(previous)
                elif names:
                    box.setCurrentIndex(0)
        if error := reply.get("error"):
            detail = "\n".join(str(line) for item in reply.get("records", []) if not item["ok"]
                               for line in item["output"])
            summary = error.splitlines()[0]
            if len(summary) > 108:
                summary = summary[:105] + "…"
            self._set_status(summary, "\n\n".join(filter(None, (error, detail))), problem=True)
        else:
            self._set_status(self._success)

    def _finished(self):
        self._task.deleteLater()
        self._task = None
        self._refresh_actions()
        self.busy_changed.emit(False)

