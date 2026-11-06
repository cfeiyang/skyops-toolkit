"""模拟数据生成：首次运行自动创建一份「月度项目分配管理」工作簿。

布局与真实表格一致：左列人名、上行月份、交叉格放项目号（可放多个，用「、」分隔）。
生成的数据里，张三 2026 年 11 月放了两个项目号，用来演示「同月可分配多个不同项目号」。
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from excel_store import (
    DETAIL_HEADER,
    SHEET_DETAIL,
    SHEET_SUMMARY,
    join_projects,
    month_label,
)

# 模拟的三列月份：10 月、11 月已有部分记录，12 月全空（用来验证「新周期可重新分配」）
MONTHS = [(2026, 10), (2026, 11), (2026, 12)]
PEOPLE = ["张三", "李四", "王五", "赵六"]

# (姓名, 月份) -> [(项目号, 分配时间), ...]
PRESET: Dict[Tuple[str, Tuple[int, int]], List[Tuple[str, str]]] = {
    ("张三", (2026, 10)): [("10001", "2026-10-03 10:22:15")],
    ("李四", (2026, 10)): [("10002", "2026-10-03 11:05:41")],
    ("王五", (2026, 10)): [("10003", "2026-10-05 09:12:03")],
    ("张三", (2026, 11)): [
        ("12345", "2026-11-03 10:22:15"),
        ("67890", "2026-11-06 09:30:00"),
    ],
    ("李四", (2026, 11)): [("23456", "2026-11-03 11:05:41")],
    ("王五", (2026, 11)): [("34567", "2026-11-05 15:40:09")],
}

HEAD_FILL = PatternFill("solid", fgColor="F2F4F7")
HEAD_FONT = Font(bold=True)
THIN = Side(style="thin", color="D0D5DD")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
CENTER = Alignment(horizontal="center", vertical="center")


def _style_block(sheet, rows: int, cols: int) -> None:
    for row in sheet.iter_rows(min_row=1, max_row=rows, max_col=cols):
        for cell in row:
            cell.border = BORDER
            cell.alignment = CENTER
            if cell.row == 1:
                cell.font = HEAD_FONT
                cell.fill = HEAD_FILL


def ensure_mock_workbook(path) -> Path:
    """文件不存在就生成一份模拟表；已存在则原样返回。"""
    target = Path(path)
    if target.exists():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)

    workbook = Workbook()

    # ---------------- 分配汇总 ----------------
    summary = workbook.active
    summary.title = SHEET_SUMMARY
    summary.cell(row=1, column=1, value="人员")
    for index, key in enumerate(MONTHS, start=2):
        summary.cell(row=1, column=index, value=month_label(key))
    for index, name in enumerate(PEOPLE, start=2):
        summary.cell(row=index, column=1, value=name)

    for (name, key), entries in PRESET.items():
        if name not in PEOPLE or key not in MONTHS:
            continue
        column = 2 + MONTHS.index(key)
        row = 2 + PEOPLE.index(name)
        projects = [project for project, _when in entries]
        cell = summary.cell(row=row, column=column, value=join_projects(projects))
        cell.number_format = "@"

    _style_block(summary, rows=1 + len(PEOPLE), cols=1 + len(MONTHS))
    summary.column_dimensions["A"].width = 14
    for index in range(2, 2 + len(MONTHS)):
        summary.column_dimensions[get_column_letter(index)].width = 18
    summary.freeze_panes = "B2"

    # ---------------- 分配明细 ----------------
    detail = workbook.create_sheet(SHEET_DETAIL)
    for index, title in enumerate(DETAIL_HEADER, start=1):
        detail.cell(row=1, column=index, value=title)

    offset = 2
    for (name, key), entries in PRESET.items():
        for project, when in entries:
            detail.cell(row=offset, column=1, value=month_label(key))
            detail.cell(row=offset, column=2, value=name)
            cell = detail.cell(row=offset, column=3, value=project)
            cell.number_format = "@"
            detail.cell(row=offset, column=4, value="分配")
            detail.cell(row=offset, column=5, value="")   # 原项目号：分配时为空
            detail.cell(row=offset, column=6, value=when)
            offset += 1

    _style_block(detail, rows=offset - 1, cols=len(DETAIL_HEADER))
    for index, width in enumerate((14, 12, 16, 10, 16, 22), start=1):
        detail.column_dimensions[get_column_letter(index)].width = width
    detail.freeze_panes = "A2"

    workbook.save(target)
    return target
