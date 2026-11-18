"""STK 12 仿真工作台."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import sys

from PySide6.QtCore import QDateTime, QThread, QTimeZone, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFont, QIcon
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDateTimeEdit, QDoubleSpinBox,
    QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy,
    QSplitter, QStackedWidget, QTabWidget, QVBoxLayout, QWidget,
)

import commands as recipes
from stk_bridge import invoke

ASSETS = Path(__file__).resolve().parent
PAGES = (
    ("场景", "新建场景、打开文件，或保存 STK 当前场景。"),
    ("卫星与星历", "按轨道根数创建卫星，也可导入已有星历、粘贴 TLE 或导出星历。"),
    ("地面站", "输入大地经纬度和高程，将地面站添加到当前场景。"),
    ("角度约束", "设置地面站与卫星的 Access 条件，之后重新计算可见时段。"),
    ("可见性分析", "选择地面站和卫星，计算所选对象在场景时间范围内的可见时段。"),
    ("命令终端", "每行输入一条 Connect 命令。支持打开本工具保存的命令文件。"),
)
STYLES = """
QWidget { font-family: "Segoe UI", "Microsoft YaHei UI"; font-size: 14px; color: #162b3c; }
QMainWindow, QWidget#Workspace, QScrollArea, QScrollArea > QWidget > QWidget { background: #edf3f5; }
QFrame#Header { background: #ffffff; border-bottom: 1px solid #d9e5e9; }
QFrame#Sidebar { background: #142b3a; }
QLabel#SideCaption { color: #a7bbc6; font-size: 12px; font-weight: 600; }
QPushButton#Nav { background: transparent; border: 0; text-align: left; padding: 11px 12px; color: #d6e4ea; }
QPushButton#Nav:hover { background: #203d4d; }
QPushButton#Nav:checked { background: #23635c; color: #ffffff; font-weight: 650; }
QLabel#SideFoot { color: #9fb5c1; font-size: 12px; }
QLabel#Title { font-size: 21px; font-weight: 700; }
QLabel#PageTitle { font-size: 27px; font-weight: 700; }
QLabel#Section { font-size: 16px; font-weight: 650; }
QLabel#Muted { color: #506674; font-size: 13px; }
QLabel#Error { color: #a22e34; font-size: 13px; }
QLabel#Status { background: #edf3f5; color: #415c68; border-radius: 8px; padding: 7px 12px; }
QLabel#Status[connected="true"] { background: #e4f3ec; color: #145d45; }
QFrame#Card { background: #ffffff; border: 1px solid #d9e5e9; border-radius: 13px; }
QFrame#Footer { background: #ffffff; border-top: 1px solid #d9e5e9; }
QPushButton { min-height: 20px; padding: 8px 12px; border: 1px solid #cddce1;
              border-radius: 7px; background: #ffffff; font-weight: 550; }
QPushButton:hover { background: #eaf5f2; border-color: #86b3a9; }
QPushButton:pressed { background: #e0eeea; }
QPushButton:disabled { color: #778892; background: #edf1f3; border-color: #dce6ea; }
QPushButton#Primary { background: #17695d; color: #ffffff; border-color: #17695d; font-weight: 700; }
QPushButton#Primary:hover { background: #10564c; }
QPushButton#Primary:disabled { color: #6f8680; background: #e5efec; border-color: #d8e7e2; }
QLineEdit, QComboBox, QDoubleSpinBox, QDateTimeEdit {
    min-height: 24px; padding: 6px 9px; border: 1px solid #cbdadf;
    border-radius: 6px; background: #ffffff; selection-background-color: #206d60; }
QComboBox:editable QLineEdit { border: 0; padding: 0; }
QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QDateTimeEdit:focus {
    border-color: #278876; }
QCheckBox { spacing: 8px; }
QPlainTextEdit { font-family: "Consolas", "Microsoft YaHei UI"; font-size: 13px; border: 1px solid #d3e1e5; border-radius: 7px;
    background: #f4f8f9; selection-background-color: #287e71; padding: 8px; }
QPlainTextEdit#Console { background: #122a38; color: #d8eee9; border: 1px solid #122a38; }
QTabWidget::pane { border: 0; }
QTabBar::tab { padding: 8px 12px; color: #526b79; background: #eff4f5; border-radius: 6px; margin-right: 4px; }
QTabBar::tab:selected { background: #e4f1ed; color: #155c52; font-weight: 650; }
QSplitter::handle { background: transparent; }
"""


def label(text, role=""):
    item = QLabel(text)
    item.setTextFormat(Qt.TextFormat.PlainText)
    item.setObjectName(role)
    item.setWordWrap(True)
    return item


def button(text, action, role=""):
    item = QPushButton(text)
    item.setObjectName(role)
    item.clicked.connect(action)
    return item


def choice(items, *, editable=False):
    item = QComboBox()
    item.setEditable(editable)
    if editable:
        item.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
    for title, data in items:
        item.addItem(title, data)
    return item


def numeric(value, minimum, maximum, places=3):
    item = QDoubleSpinBox()
    item.setDecimals(places)
    item.setRange(minimum, maximum)
    item.setValue(value)
    item.setKeyboardTracking(False)
    return item


def terminal(readonly=True):
    item = QPlainTextEdit()
    item.setReadOnly(readonly)
    if readonly:
        item.setObjectName("Console")
    mono = QFont("Consolas")
    mono.setPointSize(10)
    item.setFont(mono)
    item.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
    return item


class Form:
    def __init__(self, heading, note):
        self.widget = QWidget()
        self.layout = QVBoxLayout(self.widget)
        self.layout.setContentsMargins(1, 0, 5, 8)
        self.layout.setSpacing(10)
        self.layout.addWidget(label(heading, "PageTitle"))
        self.layout.addWidget(label(note, "Muted"))
        card = QFrame()
        card.setObjectName("Card")
        self.grid = QGridLayout(card)
        self.grid.setContentsMargins(15, 17, 15, 17)
        self.grid.setHorizontalSpacing(13)
        self.grid.setVerticalSpacing(12)
        self.grid.setColumnStretch(1, 1)
        self.grid.setColumnMinimumWidth(0, 120)
        self.layout.addWidget(card)
        self.row = 0

    def add(self, caption, widget):
        caption_widget = label(caption)
        caption_widget.setBuddy(widget)
        self.grid.addWidget(caption_widget, self.row, 0)
        self.grid.addWidget(widget, self.row, 1)
        self.row += 1
        return (caption_widget, widget)

    def note(self, text):
        item = label(text, "Muted")
        self.grid.addWidget(item, self.row, 0, 1, 2)
        self.row += 1
        return item

    def finish(self):
        self.layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(self.widget)
        return scroll


class Worker(QThread):
    reply = Signal(dict)

    def __init__(self, action, plan, expected_scenario, parent):
        super().__init__(parent)
        self.action = action
        self.plan = plan
        self.expected_scenario = expected_scenario

    def run(self):
        try:
            self.reply.emit(invoke(self.action, self.plan, self.expected_scenario))
        except Exception as error:
            self.reply.emit({"error": str(error)})


class Workbench(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("STK 12 仿真工作台")
        self.setWindowIcon(QIcon(str(ASSETS / "workbench.ico")))
        self.resize(1230, 760)
        self.setMinimumSize(940, 620)
        self.plan = None
        self.worker = None
        self.connected_scenario = ""
        self.batch = False
        self.nav = []
        self.target_selectors = []
        self.watched = []
        self.build()
        self.setup_demo()
        self.navigate(0)

    def build(self):
        base = QWidget(objectName="Workspace")
        self.setCentralWidget(base)
        whole = QVBoxLayout(base)
        whole.setContentsMargins(0, 0, 0, 0)
        whole.setSpacing(0)

        header = QFrame(objectName="Header")
        bar = QHBoxLayout(header)
        bar.setContentsMargins(19, 12, 19, 12)
        bar.setSpacing(9)
        mark = QLabel()
        mark.setPixmap(self.windowIcon().pixmap(36, 36))
        bar.addWidget(mark)
        bar.addWidget(label("STK 12 仿真工作台", "Title"))
        bar.addStretch(1)
        self.status = label("离线 · 可生成命令", "Status")
        self.status.setWordWrap(False)
        bar.addWidget(self.status)
        self.start_stk = button("启动 / 连接 STK", lambda: self.run_action("start"))
        bar.addWidget(self.start_stk)
        whole.addWidget(header)

        middle = QHBoxLayout()
        middle.setContentsMargins(0, 0, 0, 0)
        middle.setSpacing(0)
        side = QFrame(objectName="Sidebar")
        side.setFixedWidth(177)
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(12, 17, 12, 15)
        side_layout.setSpacing(7)
        side_layout.addWidget(label("仿真流程", "SideCaption"))
        for index, (title, _) in enumerate(PAGES):
            text = f"{index + 1}    {title}" if index < 5 else f"     {title}"
            entry = button(text, lambda checked=False, i=index: self.navigate(i), "Nav")
            entry.setCheckable(True)
            self.nav.append(entry)
            side_layout.addWidget(entry)
        side_layout.addStretch()
        side_layout.addWidget(button("官方 Connect 教程", self.open_tutorial, "Nav"))
        side_layout.addWidget(label("Ansys STK 12 Desktop", "SideFoot"))
        middle.addWidget(side)

        area = QWidget()
        area_layout = QHBoxLayout(area)
        area_layout.setContentsMargins(15, 17, 15, 14)
        area_layout.setSpacing(0)
        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        split.setHandleWidth(10)
        self.pages = QStackedWidget()
        self.build_pages()
        split.addWidget(self.pages)

        right = QFrame(objectName="Card")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(13, 12, 13, 12)
        right_layout.setSpacing(8)
        right_header = QHBoxLayout()
        self.preview_heading = label("当前步骤", "Section")
        right_header.addWidget(self.preview_heading)
        right_header.addStretch()
        self.command_count = label("", "Muted")
        self.command_count.setWordWrap(False)
        right_header.addWidget(self.command_count)
        right_layout.addLayout(right_header)

        self.tabs = QTabWidget()
        self.preview = terminal()
        self.result = terminal()
        self.result.setPlaceholderText("运行后在这里查看 STK 返回的信息。")
        self.tabs.addTab(self.preview, "Connect 命令")
        self.tabs.addTab(self.result, "执行结果")
        right_layout.addWidget(self.tabs, 1)
        right_bar = QHBoxLayout()
        self.copy_button = button("复制命令", self.copy_commands)
        self.save_button = button("保存命令", self.save_commands)
        right_bar.addWidget(self.copy_button)
        right_bar.addWidget(self.save_button)
        right_bar.addStretch()
        right_layout.addLayout(right_bar)
        split.addWidget(right)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        split.setSizes([560, 465])
        area_layout.addWidget(split)
        middle.addWidget(area, 1)
        whole.addLayout(middle, 1)

        footer = QFrame(objectName="Footer")
        actions = QHBoxLayout(footer)
        actions.setContentsMargins(17, 10, 17, 10)
        actions.setSpacing(8)
        self.notice = label("", "Muted")
        self.notice.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.notice.setMinimumWidth(140)
        actions.addWidget(self.notice, 1)
        actions.addWidget(button("载入示例", self.load_demo))
        self.scope_button = button("预览整套流程", self.switch_scope)
        actions.addWidget(self.scope_button)
        self.run_button = button("执行当前步骤", lambda: self.run_action("run"), "Primary")
        actions.addWidget(self.run_button)
        whole.addWidget(footer)
        for item in self.watched:
            if isinstance(item, QComboBox):
                item.currentIndexChanged.connect(self.refresh)
            elif isinstance(item, QDateTimeEdit):
                item.dateTimeChanged.connect(self.refresh)
            elif isinstance(item, QDoubleSpinBox):
                item.valueChanged.connect(self.refresh)
            elif isinstance(item, QCheckBox):
                item.toggled.connect(self.refresh)
            else:
                item.textChanged.connect(self.refresh)
        self.satellite_name.editTextChanged.connect(
            self.follow_name("DemoSat", self.access_sat))
        self.station_name.editTextChanged.connect(
            self.follow_name("DemoStation", self.constraint_station, self.access_station))
        for item, _ in self.target_selectors:
            item.editTextChanged.connect(self.refresh)

    @staticmethod
    def follow_name(initial, *selectors):
        previous = initial

        def follow(value):
            nonlocal previous
            for selector in selectors:
                if selector.currentText() == previous:
                    selector.setEditText(value)
            previous = value

        return follow

    def field(self, widget):
        self.watched.append(widget)
        return widget

    def date_time(self):
        edit = QDateTimeEdit()
        edit.setTimeZone(QTimeZone.utc())
        edit.setDisplayFormat("yyyy-MM-dd  HH:mm:ss")
        edit.setCalendarPopup(True)
        return self.field(edit)

    def chooser(self, default, object_kind):
        box = choice([(default, None)], editable=True)
        self.target_selectors.append((box, object_kind))
        return box

    def file_box(self, edit, filters, *, save=False):
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        row.addWidget(edit, 1)

        def browse():
            if save:
                value, selected = QFileDialog.getSaveFileName(
                    self, "选择星历导出路径", edit.text(), filters,
                    options=QFileDialog.Option.DontConfirmOverwrite)
                if value and not Path(value).suffix:
                    value += ".oem" if "*.oem" in selected else ".e"
            else:
                value, _ = QFileDialog.getOpenFileName(self, "选择文件", edit.text(), filters)
            if value:
                edit.setText(str(Path(value)))
        row.addWidget(button("浏览…", browse))
        return container

    def form(self, index):
        return Form(*PAGES[index])

    def build_pages(self):
        scene = self.form(0)
        self.scene_mode = self.field(choice([("新建场景", "new"), ("打开场景文件", "open"), ("保存当前场景", "save")]))
        self.scene_name = self.field(QLineEdit())
        self.start = self.date_time()
        self.stop = self.date_time()
        self.scene_file = self.field(QLineEdit())
        scene.add("操作", self.scene_mode)
        self.scene_new = (*scene.add("场景名", self.scene_name), *scene.add("开始时间（UTC）", self.start),
                          *scene.add("结束时间（UTC）", self.stop))
        self.scene_open = scene.add("场景文件", self.file_box(self.scene_file, "STK 场景 (*.sc *.vdf)"))
        scene.note("新建时，场景历元取开始时间。若 STK 已打开场景，请先在 STK 中保存并关闭。")
        self.pages.addWidget(scene.finish())

        sat = self.form(1)
        self.sat_mode = self.field(choice([("经典轨道根数", "classical"), ("导入星历文件", "ephemeris"),
                                           ("粘贴两行 TLE", "tle"), ("导出当前星历", "export")]))
        self.satellite_name = self.chooser("DemoSat", "satellites")
        self.create_sat = self.field(QCheckBox("在当前场景创建卫星"))
        self.propagator = self.field(choice([(p, p) for p in recipes.PROPAGATORS]))
        self.frame = self.field(choice([(p, p) for p in recipes.FRAMES]))
        self.a = self.field(numeric(6878.137, 6378.138, 1000000))
        self.e = self.field(numeric(0.001, 0, 0.99999999, 8))
        self.inc = self.field(numeric(51.6, 0, 180, 6))
        self.arg = self.field(numeric(0, -360, 360, 6))
        self.raan = self.field(numeric(0, -360, 360, 6))
        self.mean = self.field(numeric(0, -360, 360, 6))
        self.step = self.field(numeric(60, .001, 86400))
        self.ephem_file = self.field(QLineEdit())
        self.export_file = self.field(QLineEdit())
        self.tle1, self.tle2 = (self.field(QLineEdit()) for _ in range(2))
        sat.add("轨道来源 / 操作", self.sat_mode)
        sat.add("卫星名", self.satellite_name)
        self.create_sat_row = sat.add("对象", self.create_sat)
        self.sat_groups = {}
        self.sat_groups["classical"] = tuple(
            item for caption, widget in (("传播器", self.propagator), ("参考系", self.frame),
            ("半长轴 a（km）", self.a), ("偏心率 e", self.e), ("倾角 i（°）", self.inc),
            ("近地点幅角 ω（°）", self.arg), ("升交点赤经 Ω（°）", self.raan),
            ("平近点角 M（°）", self.mean), ("传播步长（秒）", self.step))
            for item in sat.add(caption, widget))
        self.sat_groups["ephemeris"] = sat.add("星历文件", self.file_box(self.ephem_file, "星历 (*.e *.be *.oem)"))
        self.sat_groups["tle"] = (*sat.add("TLE 第一行", self.tle1), *sat.add("TLE 第二行", self.tle2))
        self.sat_groups["export"] = sat.add("输出路径", self.file_box(
            self.export_file, "STK 星历 (*.e);;CCSDS OEM (*.oem)", save=True))
        sat.note("轨道根数以场景开始时间为历元。取消勾选“创建卫星”可更新已有卫星。")
        self.pages.addWidget(sat.finish())

        sta = self.form(2)
        self.station_name = self.chooser("DemoStation", "stations")
        self.create_sta = self.field(QCheckBox("在当前场景创建地面站"))
        self.lat = self.field(numeric(31.2304, -90, 90, 6))
        self.lon = self.field(numeric(121.4737, -180, 180, 6))
        self.alt = self.field(numeric(10, -12000, 100000))
        self.height_type = self.field(choice([("参考椭球面", "ellipsoid"), ("平均海平面（MSL）", "msl"), ("读取场景地形", "terrain")]))
        for caption, item in (("地面站名", self.station_name), ("对象", self.create_sta),
                                 ("纬度（°）", self.lat), ("经度（°）", self.lon),
                                 ("高程基准", self.height_type), ("高程（m）", self.alt)):
            row = sta.add(caption, item)
        self.alt_row = row
        sta.note("北纬和东经输入正数。使用场景地形时，高程由 STK 读取。")
        self.pages.addWidget(sta.finish())

        con = self.form(3)
        self.constraint_station = self.chooser("DemoStation", "stations")
        con.add("应用到地面站", self.constraint_station)
        self.angle_fields = {}
        for key, title, value, low, high in (
            ("elevation", "最小仰角（°）", 10, -90, 90),
            ("sun", "太阳隔离角（°）", 15, 0, 180),
            ("moon", "月球隔离角（°）", 10, 0, 180),
            ("separation", "卫星隔离角（°）", 5, 0, 90),
        ):
            row = QWidget()
            layout = QHBoxLayout(row)
            layout.setContentsMargins(0, 0, 0, 0)
            enable = self.field(QCheckBox("设置"))
            enable.setAccessibleName(title)
            value_box = self.field(numeric(value, low, high))
            layout.addWidget(enable)
            layout.addWidget(value_box, 1)
            con.add(title, row)
            self.angle_fields[key] = (enable, value_box)
        self.reference_sat = self.chooser("", "satellites")
        self.reference_row = con.add("用于隔离的参考卫星", self.reference_sat)
        con.note("卫星隔离角指从地面站看，目标卫星方向与参考卫星方向的最小夹角。STK 会对本站已有的参考对象使用同一阈值。")
        con.note("勾选项会写入 STK。取消勾选会跳过该项，适合分次设置。")
        self.pages.addWidget(con.finish())

        acc = self.form(4)
        self.access_sat = self.chooser("DemoSat", "satellites")
        self.access_station = self.chooser("DemoStation", "stations")
        acc.add("起点地面站", self.access_station)
        acc.add("目标卫星", self.access_sat)
        acc.note("按当前场景时段计算 Access。结果将显示到右侧，可选中文字复制。")
        self.pages.addWidget(acc.finish())

        cmd = self.form(5)
        self.manual = self.field(terminal(readonly=False))
        self.manual.setMinimumHeight(260)
        self.manual.setPlaceholderText("例如  GetSTKVersion /")
        cmd.grid.addWidget(button("打开命令文件…", self.open_commands), 0, 0, 1, 2)
        cmd.grid.addWidget(self.manual, 1, 0, 1, 2)
        self.pages.addWidget(cmd.finish())

    @staticmethod
    def open_tutorial():
        QDesktopServices.openUrl(QUrl("https://help.agi.com/stk/12.10.0/Content/training/L1_Connect.htm"))

    def setup_demo(self):
        now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        for edit, value in ((self.start, now), (self.stop, now + timedelta(days=1))):
            edit.setDateTime(QDateTime.fromSecsSinceEpoch(int(value.timestamp()), QTimeZone.utc()))
        self.scene_mode.setCurrentIndex(0)
        self.scene_name.setText("GroundPassDemo")
        self.sat_mode.setCurrentIndex(0)
        self.satellite_name.setEditText("DemoSat")
        self.create_sat.setChecked(True)
        self.propagator.setCurrentIndex(0)
        self.frame.setCurrentIndex(0)
        for widget, value in ((self.a, 6878.137), (self.e, .001), (self.inc, 51.6), (self.arg, 0),
                              (self.raan, 0), (self.mean, 0), (self.step, 60)):
            widget.setValue(value)
        self.station_name.setEditText("DemoStation")
        self.create_sta.setChecked(True)
        self.height_type.setCurrentIndex(0)
        self.lat.setValue(31.2304)
        self.lon.setValue(121.4737)
        self.alt.setValue(10)
        self.constraint_station.setEditText("DemoStation")
        for key, (check, value) in self.angle_fields.items():
            check.setChecked(key == "elevation")
            value.setValue({"elevation": 10, "sun": 15, "moon": 10, "separation": 5}[key])
        self.access_sat.setEditText("DemoSat")
        self.access_station.setEditText("DemoStation")

    def load_demo(self):
        answer = QMessageBox.question(self, "载入示例", "用示例参数替换当前流程表单？")
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.setup_demo()
        self.navigate(0)
        self.switch_scope()

    def navigate(self, index):
        self.batch = False
        self.pages.setCurrentIndex(index)
        for n, item in enumerate(self.nav):
            item.setChecked(n == index)
        self.refresh()
        self.tabs.setCurrentIndex(0)

    def switch_scope(self):
        self.batch = not self.batch
        self.refresh()
        self.tabs.setCurrentIndex(0)

    def get_plan(self, index):
        if index == 0:
            if self.scene_mode.currentData() == "open":
                return recipes.open_scenario(self.scene_file.text())
            if self.scene_mode.currentData() == "save":
                return recipes.save_scenario()
            return recipes.scenario(self.scene_name.text(), self.start.dateTime().toPython(),
                                    self.stop.dateTime().toPython())
        if index == 1:
            sat = self.satellite_name.currentText()
            if self.sat_mode.currentData() == "export":
                return recipes.export_ephemeris(sat, self.export_file.text())
            return recipes.satellite(sat, self.sat_mode.currentData(), self.create_sat.isChecked(),
                propagator=self.propagator.currentData(), frame=self.frame.currentData(),
                step=self.step.value(), a_km=self.a.value(), e=self.e.value(), inc=self.inc.value(),
                arg=self.arg.value(), raan=self.raan.value(), mean=self.mean.value(),
                file=self.ephem_file.text(), tle1=self.tle1.text(), tle2=self.tle2.text())
        if index == 2:
            return recipes.station(self.station_name.currentText(), self.lat.value(), self.lon.value(),
                                   self.alt.value(), self.height_type.currentData(), self.create_sta.isChecked())
        if index == 3:
            angles = {key: value.value() if check.isChecked() else None
                      for key, (check, value) in self.angle_fields.items()}
            return recipes.constraints(self.constraint_station.currentText(),
                                       reference=self.reference_sat.currentText(), **angles)
        if index == 4:
            return recipes.access(self.access_sat.currentText(), self.access_station.currentText())
        return recipes.manual_plan(self.manual.toPlainText())

    def batch_plan(self):
        if self.scene_mode.currentData() == "save" or self.sat_mode.currentData() == "export":
            raise ValueError("整套流程需要新建或打开场景，并选择一种卫星轨道来源。保存和导出可单独执行。")
        use_constraints = any(check.isChecked() for check, _ in self.angle_fields.values())
        return recipes.Plan.combine(*(self.get_plan(i) for i in range(5) if i != 3 or use_constraints))

    def refresh(self, *_):
        for widgets, visible in ((self.scene_new, self.scene_mode.currentData() == "new"),
                                  (self.scene_open, self.scene_mode.currentData() == "open"),
                                  (self.alt_row, self.height_type.currentData() != "terrain"),
                                  (self.create_sat_row, self.sat_mode.currentData() != "export"),
                                  (self.reference_row, self.angle_fields["separation"][0].isChecked())):
            for widget in widgets:
                widget.setVisible(visible)
        for key, widgets in self.sat_groups.items():
            for widget in widgets:
                widget.setVisible(self.sat_mode.currentData() == key)
        for check, value in self.angle_fields.values():
            value.setEnabled(check.isChecked())
        self.preview_heading.setText("整套流程" if self.batch else "当前步骤")
        self.scope_button.setText("返回当前步骤" if self.batch else "预览整套流程")
        self.run_button.setText("执行整套流程" if self.batch else "执行当前步骤")
        self.plan = None
        try:
            self.plan = self.batch_plan() if self.batch else self.get_plan(self.pages.currentIndex())
            self.preview.setPlainText("\n".join(self.plan.commands))
            self.command_count.setText(f"{len(self.plan.commands)} 条命令")
            self.notice.setText("按预览顺序执行。也可复制或保存命令。" if self.batch
                                else "可先在右侧核对命令，再执行当前步骤。")
        except ValueError as error:
            self.preview.clear()
            self.command_count.clear()
            self.notice.setText(str(error))
        self.notice.setToolTip(self.notice.text())
        enabled = self.plan is not None
        self.copy_button.setEnabled(enabled)
        self.save_button.setEnabled(enabled)
        self.run_button.setEnabled(enabled and self.worker is None)

    def copy_commands(self):
        if self.plan:
            QApplication.clipboard().setText(self.preview.toPlainText())
            self.notice.setText("已复制命令。")

    def save_commands(self):
        if not self.plan:
            return
        path, _ = QFileDialog.getSaveFileName(self, "保存 Connect 命令", "stk12_connect.txt", "文本文件 (*.txt)")
        if not path:
            return
        try:
            Path(path).write_text(self.preview.toPlainText() + "\n", encoding="utf-8")
            self.notice.setText("已保存命令。")
        except OSError as error:
            QMessageBox.warning(self, "保存失败", str(error))

    def open_commands(self):
        path, _ = QFileDialog.getOpenFileName(self, "打开 Connect 命令", "", "文本文件 (*.txt *.con);;所有文件 (*)")
        if not path:
            return
        try:
            self.manual.setPlainText(Path(path).read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError) as error:
            QMessageBox.warning(self, "读取失败", str(error))

    def run_action(self, action):
        if self.worker is not None or (action == "run" and not self.plan):
            return
        plan = self.plan if action == "run" else None
        self.start_stk.setEnabled(False)
        self.run_button.setEnabled(False)
        self.notice.setText("正在执行。STK 首次启动可能需要一些时间。" if action == "start" else "正在等待 STK 返回结果。")
        self.result.clear()
        self.tabs.setCurrentIndex(1)
        self.worker = Worker(action, plan, self.connected_scenario if plan else "", self)
        self.worker.reply.connect(self.consume_reply)
        self.worker.finished.connect(self.worker_finished)
        self.worker.start()

    def consume_reply(self, reply):
        version = reply.get("version", "")
        if version:
            self.connected_scenario = reply.get("scenario", "")
            self.status.setText("已连接 · " + (self.connected_scenario or "未打开场景"))
            self.status.setToolTip(version)
            for selector, key in self.target_selectors:
                chosen = selector.currentText()
                selector.blockSignals(True)
                selector.clear()
                selector.addItems(sorted(reply.get(key, []), key=str.casefold))
                selector.setEditText(chosen)
                selector.blockSignals(False)
        else:
            self.connected_scenario = ""
            self.status.setText("离线 · 可生成命令")
            self.status.setToolTip("")
        self.status.setProperty("connected", bool(version))
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        records = reply.get("records", [])
        output = [version] if version else []
        for record in records:
            output.append(f"\n> {record['command']}")
            lines = record["output"]
            if record["ok"] and record["command"].lower().startswith("access "):
                lines = self.access_result(lines)
            output.extend(lines or ["已执行"])
        if reply.get("error"):
            output.append(f"\n{reply['error']}")
        elif not records:
            output.append("已连接 STK，可返回表单执行命令。")
        self.result.setPlainText("\n".join(output).strip())
        self.tabs.setCurrentIndex(1)
        self.notice.setText("请查看执行结果。" if reply.get("error") else f"已完成 {len(records)} 条命令。" if records else "已连接。")

    @staticmethod
    def access_result(lines):
        raw = " ".join(lines)
        if re.search(r"\bNoAccesses\b", raw, re.I):
            return ["当前约束和时段下没有可见窗口。"]
        dates = re.findall(r"\b\d{1,2} [A-Za-z]{3} \d{4} \d\d:\d\d:\d\d(?:\.\d+)?", raw)
        match = re.match(r"^\s*\S+\s+\S+\s+(\d+)\s", raw)
        if dates and match and len(dates) == 2 * int(match[1]):
            return [f"共 {len(dates) // 2} 个可见窗口", *(
                f"{i // 2 + 1:>3}. {dates[i]}  →  {dates[i + 1]}" for i in range(0, len(dates), 2))]
        return lines

    def worker_finished(self):
        self.worker.deleteLater()
        self.worker = None
        self.start_stk.setEnabled(True)
        self.run_button.setEnabled(self.plan is not None)

    def closeEvent(self, event):
        if self.worker is not None:
            self.notice.setText("请等待本次 STK 操作完成后关闭窗口。")
            event.ignore()
            return
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLES)
    window = Workbench()
    window.show()
    if sys.argv[1:] == ["--check-startup"]:
        app.processEvents()
        window.close()
        sys.exit(0)
    sys.exit(app.exec())
