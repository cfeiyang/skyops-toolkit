"""MPAM 的 PySide6 桌面界面。"""

from __future__ import annotations

import hashlib
import sqlite3
import colorsys
from collections import Counter
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtCore import QRect, Qt, QStringListModel
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QCompleter, QDialog, QFileDialog,
    QFrame, QGridLayout, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit,
    QMainWindow, QMenu, QMessageBox, QPushButton, QSizePolicy, QStackedWidget, QStyle,
    QStyledItemDelegate, QStyleOptionViewItem, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from .database import Account, AllocationStore, Database
from .excel_preview import WorkbookPreviewDialog
from .excel_store import AssignError, MonthKey, month_label, normalize_name, normalize_project_id

ASSETS = Path(__file__).resolve().parents[1] / "assets"
APP_TITLE = "月度项目分配"
STORE_ERRORS = (AssignError, OSError, sqlite3.Error)
PROJECTS_ROLE = Qt.ItemDataRole.UserRole


def label(text, style=""):
    widget = QLabel(text)
    widget.setObjectName(style)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    return widget


def button(text, action, style=""):
    widget = QPushButton(text)
    widget.setObjectName(style)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    widget.clicked.connect(action)
    return widget


def panel(padding=16):
    widget = QFrame()
    widget.setObjectName("panel")
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(padding, padding, padding, padding)
    layout.setSpacing(10)
    return widget, layout


def table(headers, widths):
    widget = QTableWidget(0, len(headers))
    widget.setHorizontalHeaderLabels(headers)
    widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    widget.setShowGrid(False)
    widget.setWordWrap(False)
    widget.setAlternatingRowColors(True)
    widget.verticalHeader().hide()
    widget.verticalHeader().setDefaultSectionSize(44)
    widget.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    for index, width in enumerate(widths):
        if width:
            widget.setColumnWidth(index, width)
        else:
            widget.horizontalHeader().setSectionResizeMode(index, QHeaderView.ResizeMode.Stretch)
    return widget


def fill_table(widget, rows):
    widget.clearContents()
    widget.setRowCount(len(rows))
    for row, values in enumerate(rows):
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            item.setToolTip(value)
            widget.setItem(row, column, item)


class Suggestions(QComboBox):
    def __init__(self, placeholder, normalize=normalize_name):
        super().__init__()
        self.normalize = normalize
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.lineEdit().setPlaceholderText(placeholder)
        self.matches = QStringListModel(self)
        completer = QCompleter(self.matches, self)
        completer.setCompletionMode(QCompleter.CompletionMode.UnfilteredPopupCompletion)
        completer.setMaxVisibleItems(8)
        self.setCompleter(completer)
        self.lineEdit().textEdited.connect(self._suggest)
        self.choices = []

    def set_choices(self, choices):
        if choices == self.choices:
            return
        self.choices = choices
        text = self.currentText()
        self.blockSignals(True)
        self.clear()
        self.addItems(choices)
        self.setCurrentIndex(-1)
        self.setEditText(text)
        self.blockSignals(False)

    def _suggest(self, value):
        text = self.normalize(value)
        matches = [item for item in self.choices if text and text in item]
        matches.sort(key=lambda item: not item.startswith(text))
        self.matches.setStringList(matches)
        if matches:
            self.completer().complete()
        else:
            self.completer().popup().hide()


class ProjectChips(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.project_colors = {}

    def set_project_colors(self, colors):
        self.project_colors = dict(colors)
        self.parent().viewport().update()

    def paint(self, painter, option, index):
        projects = index.data(PROJECTS_ROLE)
        if not projects:
            super().paint(painter, option, index)
            return
        styled = QStyleOptionViewItem(option)
        self.initStyleOption(styled, index)
        styled.text = ""
        styled.widget.style().drawControl(QStyle.ControlElement.CE_ItemViewItem, styled, painter, styled.widget)
        painter.save()
        painter.setClipRect(option.rect)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        left = option.rect.left() + 9
        right = option.rect.right() - 7
        metrics = option.fontMetrics
        for offset, name in enumerate(projects):
            available = right - left
            width = metrics.horizontalAdvance(name) + 18
            if offset and width > available:
                painter.setPen(QColor("#536783"))
                painter.drawText(QRect(left, option.rect.top(), available, option.rect.height()),
                                 Qt.AlignmentFlag.AlignVCenter, "…")
                break
            width = min(width, available - 15 if offset == 0 and len(projects) > 1 else available)
            if width < 18:
                break
            rect = QRect(left, option.rect.center().y() - 12, width, 25)
            hex_color = self.project_colors.get(name)
            if not hex_color:
                digest = hashlib.sha256(name.encode("utf-8")).digest()
                hue = int.from_bytes(digest[:2], "big") / 65535
                saturation = 0.5 + digest[2] / 255 * 0.15
                lightness = 0.43 + digest[3] / 255 * 0.1
                rgb = colorsys.hls_to_rgb(hue, lightness, saturation)
                hex_color = "#" + "".join(f"{round(channel * 255):02X}" for channel in rgb)
            project_color = QColor(hex_color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(project_color.lighter(185))
            painter.drawRoundedRect(rect, 7, 7)
            painter.setPen(project_color.darker(150))
            text = metrics.elidedText(name, Qt.TextElideMode.ElideRight, width - 12)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
            left += width + 6
        painter.restore()


def brand_mark():
    mark = label("")
    mark.setFixedSize(40, 40)
    mark.setPixmap(QIcon(str(ASSETS / "allocation.ico")).pixmap(40, 40))
    mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return mark


class PasswordDialog(QDialog):
    def __init__(self, title, action, parent, *, create_user=False, ask_current=False):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(385)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        self.user = QLineEdit()
        self.role = QComboBox()
        self.role.addItems(["操作员", "管理员"])
        self.current = QLineEdit()
        self.password = QLineEdit()
        self.confirm = QLineEdit()
        for field in (self.current, self.password, self.confirm):
            field.setEchoMode(QLineEdit.EchoMode.Password)
        if create_user:
            for title, field in (("账号", self.user), ("角色", self.role)):
                layout.addWidget(label(title, "fieldLabel"))
                layout.addWidget(field)
        if ask_current:
            layout.addWidget(label("当前密码", "fieldLabel"))
            layout.addWidget(self.current)
        for title, field in (("新密码", self.password), ("确认密码", self.confirm)):
            layout.addWidget(label(title, "fieldLabel"))
            layout.addWidget(field)
        self.error = label("", "error")
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        submit = button("保存", lambda: self.submit(action), "primary")
        submit.setDefault(True)
        layout.addWidget(submit)

    def submit(self, action):
        if self.password.text() != self.confirm.text():
            self.error.setText("两次输入的密码不一致。")
            return
        try:
            action(self)
        except STORE_ERRORS as error:
            self.error.setText(str(error))
            return
        self.accept()


class LoginDialog(QDialog):
    def __init__(self, database):
        super().__init__()
        self.database = database
        self.setup = not database.has_accounts()
        self.account = None
        self.setWindowTitle("创建管理员 · 月度项目分配" if self.setup else "登录 · 月度项目分配")
        self.setFixedWidth(424)
        self.failures = 0
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        card, content = panel(24)
        layout.addWidget(card)
        content.addWidget(brand_mark())
        content.addWidget(label("月度项目分配", "pageTitle"))
        content.addWidget(label("首次使用，请创建本机管理员。" if self.setup else "登录后继续查看本机分配记录。", "muted"))
        self.user = QLineEdit()
        self.user.setPlaceholderText("输入账号")
        self.password = QLineEdit()
        self.password.setPlaceholderText("输入密码")
        self.confirm = QLineEdit()
        for field in (self.password, self.confirm):
            field.setEchoMode(QLineEdit.EchoMode.Password)
        fields = [("账号", self.user), ("密码", self.password)]
        if self.setup:
            fields.append(("确认密码", self.confirm))
        for title, field in fields:
            content.addWidget(label(title, "fieldLabel"))
            content.addWidget(field)
        self.error = label("", "error")
        self.error.setWordWrap(True)
        self.error.hide()
        content.addWidget(self.error)
        submit = button("创建管理员" if self.setup else "登录", self.submit, "primary")
        submit.setDefault(True)
        content.addWidget(submit)
        self.user.setFocus()

    def submit(self):
        try:
            if self.setup:
                if self.password.text() != self.confirm.text():
                    raise AssignError("两次输入的密码不一致。")
                account = self.database.create_admin(self.user.text(), self.password.text())
            else:
                account = self.database.authenticate(self.user.text(), self.password.text())
                if account is None:
                    self.failures += 1
                    self.password.clear()
                    if self.failures >= 3:
                        QMessageBox.warning(self, "登录失败", "连续 3 次输入错误，程序退出。")
                        self.reject()
                        return
                    raise AssignError(f"账号或密码错误，或账号已停用（{self.failures}/3）。")
                if account.must_change:
                    change = PasswordDialog(
                        "首次登录 · 修改密码",
                        lambda form: self.database.change_password(
                            account.username, self.password.text(), form.password.text(),
                        ),
                        self,
                    )
                    if change.exec() != QDialog.DialogCode.Accepted:
                        return
                    account = self.database.require_account(account.username)
        except STORE_ERRORS as error:
            self.error.setText(str(error))
            self.error.show()
            return
        self.account = account
        self.password.clear()
        self.confirm.clear()
        self.accept()


class AccountManager(QDialog):
    def __init__(self, database, actor, parent):
        super().__init__(parent)
        self.database = database
        self.actor = actor
        self.setWindowTitle("账号管理")
        self.resize(650, 430)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.addWidget(label("本机账号", "sectionTitle"))
        layout.addWidget(label("新建或重置账号后，使用者需在首次登录时设置自己的密码。", "muted"))
        self.table = table(("账号", "角色", "状态"), (0, 114, 135))
        layout.addWidget(self.table, 1)
        actions = QHBoxLayout()
        actions.addWidget(button("新增账号", self.create_user, "primary"))
        self.role = button("更改角色", self.change_role)
        self.reset = button("重置密码", self.reset_password)
        self.toggle = button("停用账号", self.toggle_user)
        for widget in (self.role, self.reset, self.toggle):
            actions.addWidget(widget)
        actions.addStretch()
        layout.addLayout(actions)
        self.table.itemSelectionChanged.connect(self.update_selection)
        self.refresh()

    def refresh(self):
        self.accounts = self.database.users(self.actor)
        fill_table(self.table, [
            (account.username, "管理员" if account.admin else "操作员",
             "已停用" if not account.enabled else "待修改密码" if account.must_change else "已启用")
            for account in self.accounts
        ])
        self.update_selection()

    def selected(self):
        rows = self.table.selectionModel().selectedRows()
        return self.accounts[rows[0].row()] if rows else None

    def update_selection(self):
        account = self.selected()
        editable = account is not None and account.username != self.actor
        self.role.setEnabled(editable)
        self.reset.setEnabled(editable)
        self.toggle.setEnabled(editable)
        self.toggle.setText("启用账号" if account and not account.enabled else "停用账号")

    def create_user(self):
        dialog = PasswordDialog(
            "新增账号",
            lambda form: self.database.create_user(
                self.actor, form.user.text(), form.password.text(), admin=form.role.currentIndex() == 1,
            ),
            self, create_user=True,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def reset_password(self):
        account = self.selected()
        if account:
            dialog = PasswordDialog(
                f"重置密码 · {account.username}",
                lambda form: self.database.reset_password(self.actor, account.username, form.password.text()),
                self,
            )
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.refresh()

    def toggle_user(self):
        account = self.selected()
        if not account:
            return
        try:
            self.database.set_user_enabled(self.actor, account.username, not account.enabled)
            self.refresh()
        except STORE_ERRORS as error:
            QMessageBox.warning(self, "无法更改状态", str(error))

    def change_role(self):
        account = self.selected()
        if not account:
            return
        role, accepted = QInputDialog.getItem(
            self, "更改角色", account.username, ["操作员", "管理员"], int(account.admin), False,
        )
        if accepted:
            try:
                self.database.set_user_role(self.actor, account.username, role == "管理员")
                self.refresh()
            except STORE_ERRORS as error:
                QMessageBox.warning(self, "无法更改角色", str(error))


class MonthDialog(QDialog):
    def __init__(self, key, parent):
        super().__init__(parent)
        self.setWindowTitle("选择分配月份")
        self.key = key
        self.year = key[0]
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        header = QHBoxLayout()
        self.year_label = label("", "sectionTitle")
        self.year_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(button("‹", lambda: self.set_year(self.year - 1), "compact"))
        header.addWidget(self.year_label, 1)
        header.addWidget(button("›", lambda: self.set_year(self.year + 1), "compact"))
        layout.addLayout(header)
        months = QGridLayout()
        self.buttons = []
        for month in range(1, 13):
            cell = button(f"{month} 月", lambda checked=False, value=month: self.choose(value))
            cell.setCheckable(True)
            self.buttons.append(cell)
            row, column = divmod(month - 1, 4)
            months.addWidget(cell, row, column)
        layout.addLayout(months)
        self.set_year(self.year)

    def set_year(self, year):
        self.year = max(1900, min(2200, year))
        self.year_label.setText(f"{self.year} 年")
        for index, month in enumerate(self.buttons, 1):
            month.setChecked((self.year, index) == self.key)

    def choose(self, month):
        self.key = (self.year, month)
        self.accept()


class App(QMainWindow):
    def __init__(self, database: Database, account: Account):
        super().__init__()
        self.database = database
        self.account = account
        self.username = account.username
        active = database.active_workbook()
        self.store = AllocationStore(database, active, self.username) if active is not None else None
        self.month_key: MonthKey
        self.month_rows = []
        self.editing = False
        self.current_view = "allocation"

        self.setWindowTitle(APP_TITLE)
        self.resize(1180, 744)
        self.setMinimumSize(900, 590)
        shell = QWidget()
        shell.setObjectName("workspace")
        self.setCentralWidget(shell)
        layout = QVBoxLayout(shell)
        layout.setContentsMargins(24, 18, 24, 12)
        layout.setSpacing(12)
        layout.addWidget(self.build_header())
        layout.addWidget(self.build_allocation(), 1)
        self.footer = label("", "muted")
        layout.addWidget(self.footer)
        self.load_store()

    def build_header(self):
        card, content = panel(0)
        row = QHBoxLayout()
        row.setContentsMargins(14, 10, 14, 10)
        row.setSpacing(12)
        content.addLayout(row)
        row.addWidget(label("当前工作簿", "muted"))
        self.file_box = QComboBox()
        self.file_box.setMinimumWidth(132)
        self.file_box.setMaximumWidth(270)
        self.file_box.currentIndexChanged.connect(self.switch_workbook)
        row.addWidget(self.file_box)
        self.preview_button = button("预览数据…", self.preview_workbook)
        row.addWidget(self.preview_button)
        row.addWidget(button("导入 Excel…", self.import_excel))
        self.export_button = button("导出副本…", self.export_workbook)
        row.addWidget(self.export_button)
        row.addStretch()
        account_button = QPushButton(self.username.replace("&", "&&"))
        account_button.setMaximumWidth(142)
        account_button.setToolTip(self.username)
        menu = QMenu(account_button)
        menu.addAction("修改密码", self.change_password)
        if self.account.admin:
            menu.addAction("账号管理", self.manage_accounts)
        account_button.setMenu(menu)
        row.addWidget(account_button)
        return card

    def build_allocation(self):
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        card, content = panel(0)
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(14, 12, 14, 2)
        toolbar.setSpacing(7)
        self.prev_month = button("‹", lambda: self.step_month(-1), "compact")
        self.month_button = button("", self.pick_month)
        self.next_month = button("›", lambda: self.step_month(1), "compact")
        for widget, title in ((self.prev_month, "上个月"), (self.next_month, "下个月")):
            widget.setToolTip(title)
            widget.setAccessibleName(title)
        for widget in (self.prev_month, self.month_button, self.next_month):
            toolbar.addWidget(widget)
        toolbar.addStretch()
        self.data_mode_button = button("分配数据", lambda: self.show_month_view("allocation"), "viewToggle")
        self.history_mode_button = button("变更记录", lambda: self.show_month_view("history"), "viewToggle")
        for widget in (self.data_mode_button, self.history_mode_button):
            widget.setCheckable(True)
            toolbar.addWidget(widget)
        self.data_mode_button.setChecked(True)
        content.addLayout(toolbar)

        filter_row = QHBoxLayout()
        filter_row.setContentsMargins(14, 0, 14, 4)
        filter_row.setSpacing(8)
        self.filter_mode = QComboBox()
        self.filter_mode.setAccessibleName("筛选方式")
        self.filter_mode.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        for title, mode in (("按人员", "person"), ("按项目号", "project"), ("未分配", "unassigned"), ("已分配", "assigned")):
            self.filter_mode.addItem(title, mode)
        self.filter_text = QLineEdit()
        self.filter_text.setAccessibleName("筛选关键词")
        self.filter_text.setClearButtonEnabled(True)
        filter_row.addWidget(self.filter_mode, 0, Qt.AlignmentFlag.AlignLeft)
        filter_row.addWidget(self.filter_text, 1)
        self.filter_spacer = QWidget()
        self.filter_spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.filter_spacer.hide()
        filter_row.addWidget(self.filter_spacer, 1)
        self.filter_mode.currentIndexChanged.connect(self.change_allocation_filter)
        self.filter_text.textChanged.connect(self.filter_month_rows)
        self.history_filters = QWidget()
        history_filter_layout = QHBoxLayout(self.history_filters)
        history_filter_layout.setContentsMargins(0, 0, 0, 0)
        history_filter_layout.setSpacing(8)
        self.change_person = QLineEdit()
        self.change_person.setPlaceholderText("筛选人员")
        self.change_project = QLineEdit()
        self.change_project.setPlaceholderText("筛选项目号")
        self.change_operator = QLineEdit()
        self.change_operator.setPlaceholderText("筛选操作账号")
        for field in (self.change_person, self.change_project, self.change_operator):
            field.setClearButtonEnabled(True)
            field.textChanged.connect(self.refresh_changes)
            history_filter_layout.addWidget(field, 1)
        self.history_filters.hide()
        filter_row.addWidget(self.history_filters, 1)
        content.addLayout(filter_row)

        self.allocation_table = table(("人员", "项目号", "状态", "最近操作", "操作"), (100, 0, 124, 158, 139))
        self.project_delegate = ProjectChips(self.allocation_table)
        self.allocation_table.setItemDelegateForColumn(1, self.project_delegate)
        self.allocation_table.cellDoubleClicked.connect(self.open_row_from_double_click)
        self.change_count = label("", "muted")
        self.change_table = table(
            ("操作时间", "操作人", "人员", "操作", "项目号变化"),
            (158, 115, 100, 66, 0),
        )
        self.allocation_view = QStackedWidget()
        self.allocation_view.addWidget(self.allocation_table)
        self.allocation_view.addWidget(self.change_table)
        empty = QWidget()
        empty_layout = QVBoxLayout(empty)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_title = label("", "sectionTitle")
        self.empty_text = label("", "muted")
        for widget in (self.empty_title, self.empty_text):
            widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_layout.addWidget(widget)
        self.empty_open = button("导入 Excel…", self.import_excel, "primary")
        self.empty_add = button("录入首条分配", lambda: self.open_editor("", []), "primary")
        empty_layout.addSpacing(8)
        empty_layout.addWidget(self.empty_open, alignment=Qt.AlignmentFlag.AlignHCenter)
        empty_layout.addWidget(self.empty_add, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.allocation_view.addWidget(empty)
        content.addWidget(self.change_count)
        content.addWidget(self.allocation_view, 1)
        content.setContentsMargins(1, 1, 1, 5)
        layout.addWidget(card, 1)

        self.editor = self.build_editor()
        layout.addWidget(self.editor)
        self.editor.hide()
        return page


    def build_editor(self):
        card, content = panel()
        card.setFixedWidth(292)
        header = QHBoxLayout()
        self.editor_title = label("", "sectionTitle")
        header.addWidget(self.editor_title, 1)
        close = button("×", self.close_editor, "compact")
        close.setAccessibleName("关闭分配面板")
        header.addWidget(close)
        content.addLayout(header)
        self.editor_month = label("", "muted")
        content.addWidget(self.editor_month)
        content.addSpacing(8)

        self.person_box = Suggestions("输入姓名或选择人员")
        self.person_box.editTextChanged.connect(self.update_editor)
        self.old_label = label("原项目号", "fieldLabel")
        self.old_box = QComboBox()
        self.old_box.currentIndexChanged.connect(self.update_editor)
        self.project_label = label("项目号", "fieldLabel")
        self.project_box = Suggestions("输入项目号", normalize_project_id)
        self.project_box.editTextChanged.connect(self.update_editor)
        self.project_box.lineEdit().returnPressed.connect(self.submit_editor)
        for widget in (
            label("人员", "fieldLabel"), self.person_box, self.old_label, self.old_box,
            self.project_label, self.project_box,
        ):
            content.addWidget(widget)
        self.editor_hint = label("", "note")
        self.editor_hint.setWordWrap(True)
        content.addWidget(self.editor_hint)
        self.save_button = button("", self.submit_editor, "primary")
        content.addWidget(self.save_button)
        self.manage = QWidget()
        actions = QHBoxLayout(self.manage)
        actions.setContentsMargins(0, 0, 0, 0)
        actions.addWidget(button("新增人员", self.add_person))
        actions.addWidget(button("登记项目号", self.add_project))
        content.addWidget(self.manage)
        content.addStretch()
        return card

    def refresh_changes(self):
        rows = self.store.history(
            person=normalize_name(self.change_person.text()),
            operator=normalize_name(self.change_operator.text()),
            key=self.month_key,
            project=normalize_project_id(self.change_project.text()),
        ) if self.store else []
        fill_table(self.change_table, [
            (when or "—", operator or "未记录", person, action, f"{old or '—'} → {project or '—'}")
            for key, person, action, old, project, when, operator in rows
        ])
        self.change_count.setText(f"{month_label(self.month_key)} · 共 {len(rows)} 条变更" if self.store else "导入 Excel 后即可查看变更记录")
        if self.current_view == "history":
            self.allocation_view.setCurrentIndex(1 if rows else 2)
            if not rows:
                filtered = any((self.change_person.text(), self.change_project.text(), self.change_operator.text()))
                self.empty_title.setText("没有符合条件的变更记录" if filtered else "本月暂无变更记录")
                self.empty_text.setText(
                    "调整或清除筛选条件后再查看。" if filtered
                    else "调整月份，也可以在分配数据中新增或修改项目号。"
                )
                self.empty_open.hide()
                self.empty_add.hide()

    def change_password(self):
        PasswordDialog(
            "修改密码",
            lambda form: self.database.change_password(self.username, form.current.text(), form.password.text()),
            self, ask_current=True,
        ).exec()

    def manage_accounts(self):
        try:
            AccountManager(self.database, self.username, self).exec()
        except STORE_ERRORS as error:
            QMessageBox.warning(self, "无法打开账号管理", str(error))

    def import_excel(self):
        folder = str(self.store.path.parent) if self.store else ""
        path, _ = QFileDialog.getOpenFileName(self, "导入分配工作簿", folder, "Excel 工作簿 (*.xlsx)")
        if path:
            self.open_workbook(path)

    def preview_workbook(self):
        if not self.store:
            return
        try:
            with TemporaryDirectory(prefix="mpam-preview-") as directory:
                path = Path(directory) / "preview.xlsx"
                self.store.export(path)
                preview = WorkbookPreviewDialog(
                    path, self, on_import=self.import_excel, on_export=self.export_workbook,
                )
                preview.exec()
        except Exception as error:
            QMessageBox.warning(self, "预览失败", str(error))

    def open_workbook(self, path):
        try:
            workbook = self.database.import_workbook(Path(path), self.username)
            self.store = AllocationStore(self.database, workbook, self.username)
        except Exception as error:
            QMessageBox.warning(self, "导入失败", str(error))
            return
        self.load_store()
        self.update_footer("已打开本地分配数据")

    def switch_workbook(self):
        workbook = self.file_box.currentData()
        if workbook is None or (self.store and self.store.workbook == workbook):
            return
        try:
            self.database.require_account(self.username)
            self.database.select_workbook(workbook)
            self.store = AllocationStore(self.database, workbook, self.username)
            self.load_store()
        except STORE_ERRORS as error:
            QMessageBox.warning(self, "无法切换工作簿", str(error))

    def export_workbook(self):
        if not self.store:
            return
        suggestion = self.store.path.with_name(f"{self.store.path.stem}-分配副本.xlsx")
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 Excel 副本", str(suggestion), "Excel 工作簿 (*.xlsx)",
            options=QFileDialog.Option.DontConfirmOverwrite,
        )
        if not path:
            return
        try:
            target = Path(path)
            if not target.suffix:
                target = target.with_suffix(".xlsx")
            self.store.export(target)
        except (AssignError, OSError, sqlite3.Error, ValueError) as error:
            QMessageBox.warning(self, "导出失败", str(error))
            return
        self.update_footer(f"已导出 {target.name}")

    def load_store(self):
        loaded = self.store is not None
        today = datetime.now()
        self.month_key = (today.year, today.month)
        if loaded:
            keys = self.store.month_keys()
            if keys and self.month_key not in keys:
                self.month_key = next((key for key in reversed(keys) if key <= self.month_key), keys[0])
        self.file_box.blockSignals(True)
        self.file_box.clear()
        books = self.database.workbooks()
        if loaded:
            names = Counter(book["name"] for book in books)
            for book in books:
                title = book["name"]
                if names[title] > 1:
                    title = f"#{book['id']} · {title}"
                self.file_box.addItem(title, book["id"])
                self.file_box.setItemData(self.file_box.count() - 1, book["source"], Qt.ItemDataRole.ToolTipRole)
            self.file_box.setCurrentIndex(self.file_box.findData(self.store.workbook))
            self.file_box.setToolTip(str(self.store.path))
        else:
            self.file_box.addItem("未导入工作簿")
        self.file_box.setEnabled(loaded)
        self.file_box.blockSignals(False)
        self.project_delegate.set_project_colors(self.store.project_color_map if self.store else {})
        self.editor.hide()
        self.filter_text.clear()
        self.filter_mode.setCurrentIndex(0)
        for widget in (
            self.prev_month, self.next_month, self.month_button,
            self.filter_mode, self.filter_text, self.export_button,
            self.preview_button,
            self.data_mode_button, self.history_mode_button,
            self.change_person, self.change_project, self.change_operator,
        ):
            widget.setEnabled(loaded)
        self.refresh_choices()
        self.change_person.clear()
        self.change_project.clear()
        self.change_operator.clear()
        self.show_month_view("allocation")
        self.refresh_month()
        self.refresh_changes()
        self.update_footer()

    def refresh_choices(self):
        self.person_box.set_choices(self.store.people() if self.store else [])
        self.project_box.set_choices(self.store.all_project_ids() if self.store else [])

    def refresh_month(self):
        self.month_button.setText(month_label(self.month_key))
        self.editor_month.setText(f"分配月份  ·  {month_label(self.month_key)}")
        self.month_rows = []
        if self.store:
            for name in self.store.people():
                projects = self.store.projects_of(self.month_key, name)
                recent = self.store.assigned_at(self.month_key, name)
                self.month_rows.append((name, projects, recent))
        self.filter_month_rows()
        self.refresh_changes()

    def change_allocation_filter(self):
        if self.filter_text.text():
            self.filter_text.clear()
        else:
            self.filter_month_rows()

    def filter_month_rows(self):
        mode = self.filter_mode.currentData()
        query = self.filter_text.text()
        searching = mode in ("person", "project")
        self.filter_text.setVisible(searching and self.current_view == "allocation")
        self.filter_spacer.setVisible(not searching and self.current_view == "allocation")
        if mode == "project":
            self.filter_text.setPlaceholderText("输入完整项目号")
            project = normalize_project_id(query)
            rows = [row for row in self.month_rows if not project or project in row[1]]
        elif mode == "person":
            self.filter_text.setPlaceholderText("输入姓名")
            person = normalize_name(query)
            rows = [row for row in self.month_rows if person in row[0]]
        else:
            rows = [row for row in self.month_rows if bool(row[1]) == (mode == "assigned")]
        if self.current_view == "allocation":
            self.allocation_view.setCurrentIndex(0 if rows else 2)
        if not rows:
            self.empty_open.setVisible(self.store is None)
            self.empty_add.setVisible(self.store is not None and not self.month_rows)
            if not self.store:
                self.empty_title.setText("导入你的分配工作簿")
                self.empty_text.setText("从 Excel 读取现有分配，之后可在本机继续编辑。")
            elif self.month_rows:
                self.empty_title.setText("当月没有符合条件的记录")
                self.empty_text.setText("可以调整筛选条件或切换月份。")
            else:
                self.empty_title.setText("工作簿暂无人员")
                self.empty_text.setText("录入首条分配时可以同时新增人员。")
        values = []
        for name, projects, recent in rows:
            status = f"需整理（{len(projects)} 项）" if len(projects) > 1 else ("已分配" if projects else "未分配")
            values.append((name, "、".join(projects) or "—", status, recent or "—"))
        fill_table(self.allocation_table, values)
        for index, (name, projects, _) in enumerate(rows):
            self.allocation_table.item(index, 1).setData(PROJECTS_ROLE, projects)
            status_color = "#a55b10" if len(projects) > 1 else ("#23614c" if projects else "#596679")
            self.allocation_table.item(index, 2).setForeground(QColor(status_color))
            actions = QWidget()
            action_layout = QHBoxLayout(actions)
            action_layout.setContentsMargins(4, 0, 4, 0)
            action_layout.setSpacing(3)
            if len(projects) > 1:
                clean = button(
                    "整理", lambda checked=False, person=name, ids=projects: self.resolve_multiple(person, ids),
                    "rowAction",
                )
                clean.setAccessibleName(f"为{name}整理项目号，保留一个")
                clean.setToolTip("选择一个保留，其余会记入变更记录")
                action_layout.addWidget(clean)
            elif projects:
                edit = button("修改", lambda checked=False, row=index: self.open_row(row), "rowAction")
                edit.setAccessibleName(f"修改{name}的项目号")
                action_layout.addWidget(edit)
            else:
                add = button("新增分配", lambda checked=False, person=name: self.open_editor(person, []), "rowAction")
                add.setAccessibleName(f"为{name}新增分配")
                action_layout.addWidget(add)
            action_layout.addStretch()
            self.allocation_table.setCellWidget(index, 4, actions)

    def pick_month(self):
        picker = MonthDialog(self.month_key, self)
        if picker.exec() == QDialog.DialogCode.Accepted:
            self.set_month(picker.key)

    def step_month(self, delta):
        year, month = self.month_key
        year, offset = divmod(year * 12 + month - 1 + delta, 12)
        self.set_month((year, offset + 1))

    def set_month(self, key):
        if 1900 <= key[0] <= 2200 and key != self.month_key:
            self.month_key = key
            self.close_editor()
            self.refresh_month()

    def show_month_view(self, view):
        self.current_view = view
        history = view == "history"
        self.data_mode_button.setChecked(not history)
        self.history_mode_button.setChecked(history)
        self.filter_mode.setVisible(not history)
        self.filter_text.setVisible(not history and self.filter_mode.currentData() in ("person", "project"))
        self.filter_spacer.setVisible(not history and self.filter_mode.currentData() not in ("person", "project"))
        self.history_filters.setVisible(history)
        self.change_count.setVisible(history)
        if history:
            self.close_editor()
            self.refresh_changes()
        else:
            self.filter_month_rows()

    def open_row_from_double_click(self, row, column):
        if column != 4:
            self.open_row(row)

    def open_row(self, row):
        name = self.allocation_table.item(row, 0).text()
        projects = self.store.projects_of(self.month_key, name)
        if len(projects) > 1:
            self.resolve_multiple(name, projects)
        elif projects:
            self.open_editor(name, projects)
        else:
            self.open_editor(name, [])

    def resolve_multiple(self, person, projects):
        keep, accepted = QInputDialog.getItem(
            self,
            "整理项目号",
            f"{person} 本月已有多个项目号。请选择唯一保留的项目号，其余会从本地分配中移除并记入变更记录。",
            projects,
            0,
            False,
        )
        if not accepted:
            return
        removed = [project for project in projects if project != keep]
        answer = QMessageBox.question(
            self,
            "确认整理",
            f"将保留「{keep}」，移除「{'、'.join(removed)}」。原始 Excel 不会修改。继续吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.store.keep_single_project(self.month_key, person, keep)
        except STORE_ERRORS as error:
            QMessageBox.warning(self, "整理失败", str(error))
            return
        self.after_write(f"已整理 {person} 的本月分配，只保留 {keep}")

    def open_editor(self, person, projects):
        self.editor.hide()
        self.editing = bool(projects)
        self.editor_title.setText("修改项目号" if self.editing else "新增分配")
        self.person_box.setEnabled(not self.editing)
        self.person_box.setEditText(person)
        self.old_box.clear()
        self.old_box.addItems(projects)
        self.old_label.setVisible(self.editing)
        self.old_box.setVisible(self.editing)
        self.manage.setVisible(not self.editing)
        self.project_label.setText("新项目号" if self.editing else "项目号")
        self.save_button.setText("保存修改" if self.editing else "确认分配")
        self.project_box.setEditText("")
        self.editor.show()
        self.update_editor()
        (self.project_box if person else self.person_box).setFocus()

    def close_editor(self):
        self.editor.hide()
        self.filter_mode.setFocus()

    def update_editor(self):
        if not self.store or self.editor.isHidden():
            return
        person = normalize_name(self.person_box.currentText())
        project = normalize_project_id(self.project_box.currentText())
        existing = self.store.projects_of(self.month_key, person)
        enabled = False
        if not person:
            hint = "选择已有人员，也可以输入新姓名。"
        elif person in self.store.duplicate_people:
            hint = "工作簿中存在同名行，请先在 Excel 中核对。"
        elif not project:
            hint = "选择或输入一个项目号。"
        elif len(project) > 40:
            hint = "项目号最多 40 个字符。"
        elif self.editing and project == self.old_box.currentText():
            hint = "新旧项目号相同。"
        elif project in existing:
            hint = f"该人员本月已有「{project}」。"
        elif not self.editing and existing:
            hint = f"该人员本月已有项目号「{existing[0]}」，每人每月只能分配一个，请使用“修改”。"
        else:
            enabled = True
            if person not in self.store.people():
                hint = f"确认后会将「{person}」加入本地人员列表。"
            else:
                hint = "保存到本机，随后可导出 Excel 副本。"
        self.editor_hint.setText(hint)
        self.save_button.setEnabled(enabled)


    def submit_editor(self):
        if self.editor.isHidden() or not self.save_button.isEnabled():
            return
        person = normalize_name(self.person_box.currentText())
        project = normalize_project_id(self.project_box.currentText())
        try:
            if self.editing:
                previous = self.old_box.currentText()
                result = self.store.replace_project(self.month_key, person, previous, project)
                message = f"已修改 {person} 的项目号   {previous} → {result}"
            else:
                result = self.store.assign(self.month_key, person, project)
                message = f"已为 {person} 分配项目号 {result}"
        except STORE_ERRORS as error:
            self.refresh_choices()
            self.refresh_month()
            self.update_editor()
            QMessageBox.warning(self, "保存失败", str(error))
            return
        self.close_editor()
        self.after_write(message)

    def add_person(self):
        name, accepted = QInputDialog.getText(self, "新增人员", "姓名", text=self.person_box.currentText())
        if not accepted or not normalize_name(name):
            return
        try:
            person = self.store.add_person(name)
        except STORE_ERRORS as error:
            QMessageBox.warning(self, "无法新增人员", str(error))
            return
        self.person_box.setEditText(person)
        self.after_write(f"已新增人员 {person}")

    def add_project(self):
        value, accepted = QInputDialog.getText(self, "登记项目号", "项目号", text=self.project_box.currentText())
        if not accepted or not normalize_project_id(value):
            return
        try:
            project = self.store.add_project(value)
        except STORE_ERRORS as error:
            QMessageBox.warning(self, "无法登记项目号", str(error))
            return
        self.project_box.setEditText(project)
        self.after_write(f"已登记项目号 {project}")

    def after_write(self, message):
        self.refresh_choices()
        self.refresh_month()
        self.update_editor()
        self.update_footer(message)

    def update_footer(self, message=""):
        text = message or ("本地数据已加载" if self.store else "等待导入工作簿")
        if self.store and self.store.last_saved:
            text += f"   ·   最近保存 {self.store.last_saved}"
        if self.username:
            text += f"   ·   {self.username}"
        self.footer.setText(text)


def create_application():
    app = QApplication([])
    app.setApplicationName(APP_TITLE)
    app.setWindowIcon(QIcon(str(ASSETS / "allocation.ico")))
    app.setStyle("Fusion")
    app.setFont(QFont("Microsoft YaHei UI", 10))
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#f2f5fa"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#18253a"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#18253a"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#dceaff"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#18253a"))
    app.setPalette(palette)
    app.setStyleSheet((ASSETS / "style.qss").read_text(encoding="utf-8"))
    return app


def run(database: Database, demo_workbook: Path | None = None) -> int:
    app = create_application()
    login = LoginDialog(database)
    if login.exec() != QDialog.DialogCode.Accepted:
        return 0
    if demo_workbook is not None:
        database.import_workbook(demo_workbook, login.account.username)
    window = App(database, login.account)
    window.show()
    return app.exec()
