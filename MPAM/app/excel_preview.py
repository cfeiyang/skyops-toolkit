"""当前 Excel 工作簿的只读预览。"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QHBoxLayout, QHeaderView, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout,
)
from openpyxl.utils import get_column_letter

from .excel_store import ExcelStore, normalize_project_id


class WorkbookPreviewDialog(QDialog):
    def __init__(self, path: Path, parent=None, on_import=None, on_export=None):
        super().__init__(parent)
        self.setWindowTitle("Excel 数据预览")
        self.resize(1360, 820)
        self.setMinimumSize(900, 600)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(10)
        layout.addWidget(QLabel(f"{path.name} · 当前本地数据的只读预览"))

        self.sheets = QTabWidget()
        layout.addWidget(self.sheets, 1)
        excel = ExcelStore(path).load()
        colors = excel.project_colors()
        workbook = excel.workbook
        for worksheet in workbook.worksheets:
            if not any(cell.value is not None for row in worksheet.iter_rows() for cell in row):
                empty = QLabel("此工作表为空")
                empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.sheets.addTab(empty, worksheet.title)
                continue
            self.sheets.addTab(self._sheet_table(worksheet, excel, colors), worksheet.title)
        workbook.close()

        footer = QHBoxLayout()
        note = QLabel("预览包含工作簿全部工作表；导入会写入本地数据库，导出会生成 Excel 副本。")
        note.setObjectName("muted")
        footer.addWidget(note, 1)
        if on_import:
            import_button = QPushButton("导入 Excel…")
            import_button.clicked.connect(lambda: self._run_action(on_import))
            footer.addWidget(import_button)
        if on_export:
            export_button = QPushButton("导出 Excel 副本…")
            export_button.setObjectName("primary")
            export_button.clicked.connect(lambda: self._run_action(on_export))
            footer.addWidget(export_button)
        close = QPushButton("关闭")
        close.clicked.connect(self.reject)
        footer.addWidget(close)
        layout.addLayout(footer)

    def _sheet_table(self, worksheet, excel: ExcelStore, colors: dict[str, str]):
        rows = max(1, worksheet.max_row)
        columns = max(1, worksheet.max_column)
        table = QTableWidget(rows, columns)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        table.setAlternatingRowColors(True)
        table.setShowGrid(True)
        table.verticalHeader().setDefaultSectionSize(30)
        table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        table.horizontalHeader().setDefaultSectionSize(118)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        table.setHorizontalHeaderLabels([get_column_letter(col) for col in range(1, columns + 1)])
        table.setVerticalHeaderLabels([str(row) for row in range(1, rows + 1)])
        for merged in worksheet.merged_cells.ranges:
            first_row, first_col, last_row, last_col = merged.min_row, merged.min_col, merged.max_row, merged.max_col
            if last_row <= rows and last_col <= columns:
                table.setSpan(first_row - 1, first_col - 1, last_row - first_row + 1, last_col - first_col + 1)

        for row in worksheet.iter_rows(min_row=1, max_row=rows, min_col=1, max_col=columns):
            for cell in row:
                if cell.value is None:
                    continue
                text = self._display_value(cell.value, cell.number_format)
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                color = excel.cell_fill_color(cell)
                if color is None:
                    color = colors.get(normalize_project_id(cell.value))
                if color:
                    item.setBackground(QColor(color))
                table.setItem(cell.row - 1, cell.column - 1, item)
        return table

    @staticmethod
    def _display_value(value, number_format: str) -> str:
        if isinstance(value, (datetime, date)):
            if "年" in number_format and "m" in number_format.lower():
                return f"{value.year}年{value.month}月"
            return value.strftime("%Y-%m-%d")
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        if isinstance(value, int):
            format_code = number_format.split(";", 1)[0]
            if format_code and set(format_code) == {"0"} and len(format_code) > len(str(abs(value))):
                return f"{value:0{len(format_code)}d}"
        return str(value)

    def _run_action(self, callback) -> None:
        self.accept()
        QTimer.singleShot(0, callback)
