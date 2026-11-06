"""Excel 读写层：分配汇总表（人员 × 月份）+ 分配明细表（只追加）。

设计要点
--------
- Excel 就是唯一数据源，不引入数据库（单人录入，没有并发）。
- 判重规则：同一人员、同一月份、同一个项目号只允许一条记录。
  同一个人在同一个月可以分配多个**不同**的项目号，只有重复的项目号才被拦截。
- 支持「修改」：把手误的项目号改成另一个，明细表记一条「修改」（含原项目号）。
- 一个单元格可存放多个项目号，用「、」分隔（如 12345、67890）。
- 每次写入前自动备份；保存走「临时文件 + 原子替换」。
- 保存时自动做两件事：
  1. 高亮 —— 同一个月里出现多次的项目号，所在格子标黄；
  2. 自适应列宽 —— 按内容（中文算 2 个字符）自动调整人员列和各月份列宽度。

表结构约定（与真实表格一致）
--------------------------
分配汇总：A1 是「人员」，第 1 行从 B 列起是月份（如 2026年11月），
          第 2 行起 A 列是人名，交叉单元格存放一个或多个项目号。
分配明细：月份 | 姓名 | 项目号 | 操作 | 原项目号 | 操作时间，只追加不修改。
"""

from __future__ import annotations

import os
import re
import shutil
import unicodedata
from collections import Counter
from copy import copy as _copy
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

SHEET_SUMMARY = "分配汇总"
SHEET_DETAIL = "分配明细"
SHEET_PROJECTS = "项目号"
DETAIL_HEADER = ("月份", "姓名", "项目号", "操作", "原项目号", "操作时间")
ACTION_ASSIGN = "分配"
ACTION_MODIFY = "修改"
ACTION_REVOKE = "撤销"

SEPARATOR = "、"
_SPLIT_RE = re.compile(r"[、/,，;；\n]+")

# 「2026年11月」「2026-11」「2026/11」「2026.11」等写法统一识别
_MONTH_RE = re.compile(r"(\d{4})\s*(?:年|[-/._])\s*(\d{1,2})")

# 同月重复项目号的高亮色（浅黄）
HIGHLIGHT_FILL = PatternFill("solid", fgColor="FFF3CD")

MonthKey = Tuple[int, int]


class AssignError(Exception):
    """业务拒绝。消息直接展示给用户，不是程序缺陷。"""


def month_label(key: MonthKey) -> str:
    return f"{key[0]}年{key[1]}月"


def parse_month_key(value) -> Optional[MonthKey]:
    """把表头单元格解析成 (年, 月)；无法识别返回 None。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return (value.year, value.month)
    if isinstance(value, date):
        return (value.year, value.month)
    match = _MONTH_RE.search(str(value))
    if not match:
        return None
    year, month = int(match.group(1)), int(match.group(2))
    if not 1 <= month <= 12:
        return None
    return (year, month)


def normalize_name(value) -> str:
    """人名归一化：全角转半角、去首尾空白。"""
    if value is None:
        return ""
    return unicodedata.normalize("NFKC", str(value)).strip()


def normalize_project_id(raw) -> str:
    """项目号归一化：全角转半角、内部空白折叠、去首尾空白。"""
    if raw is None:
        return ""
    text = unicodedata.normalize("NFKC", str(raw))
    text = re.sub(r"\s+", " ", text).strip()
    return text


def split_projects(value) -> List[str]:
    """把一个单元格里的多个项目号拆成列表（去重、保序）。"""
    if value is None:
        return []
    result: List[str] = []
    for part in _SPLIT_RE.split(str(value)):
        item = normalize_project_id(part)
        if item and item not in result:
            result.append(item)
    return result


def join_projects(items) -> str:
    return SEPARATOR.join(items)


class ExcelStore:
    """分配表的全部读写都在这里，界面层不直接碰 openpyxl。"""

    def __init__(self, path) -> None:
        self.path = Path(path)
        self._wb = None
        self._summary = None
        self._detail = None
        self._columns: Dict[MonthKey, int] = {}
        self._rows: Dict[str, int] = {}
        self._assigned_at: Dict[Tuple[MonthKey, str], str] = {}
        self._projects: List[str] = []
        self.duplicate_people: List[str] = []
        self.last_saved: Optional[str] = None
        self._header_row: int = 1

    # ------------------------------------------------------------------ 载入
    def load(self) -> "ExcelStore":
        if not self.path.is_file():
            raise AssignError(f"找不到 Excel 文件：{self.path}")
        self._wb = load_workbook(self.path)
        if not self._wb.sheetnames:
            raise AssignError("工作簿里没有任何工作表。")
        self._summary = self._pick_sheet()
        self._detail = (
            self._wb[SHEET_DETAIL] if SHEET_DETAIL in self._wb.sheetnames else None
        )
        self._header_row = self._detect_header_row()
        self._scan_month_columns()
        self._scan_people()
        self._projects = self._scan_projects()
        self._build_detail_index()
        return self

    def _pick_sheet(self):
        """优先用「分配汇总」，否则退到第一个工作表（导入真实表格时表名可能不同）。"""
        if SHEET_SUMMARY in self._wb.sheetnames:
            return self._wb[SHEET_SUMMARY]
        return self._wb[self._wb.sheetnames[0]]

    def _detect_header_row(self) -> int:
        """表头可能不在第 1 行（上方有标题），找出第一行含月份表头的行。"""
        max_row = min(self._summary.max_row, 6)
        max_col = self._summary.max_column
        fallback = 0
        for row in range(1, max_row + 1):
            hits = sum(
                1
                for col in range(2, max_col + 1)
                if parse_month_key(self._summary.cell(row=row, column=col).value)
            )
            if hits >= 2:
                return row
            if hits >= 1 and not fallback:
                fallback = row
        return fallback or 1

    def _scan_month_columns(self) -> None:
        self._columns.clear()
        for column in range(2, self._summary.max_column + 1):
            key = parse_month_key(
                self._summary.cell(row=self._header_row, column=column).value
            )
            if key is not None and key not in self._columns:
                self._columns[key] = column
        if not self._columns:
            raise AssignError(
                "没有识别到月份列。表头请写成「2026年11月」或「2026-11」，"
                "并且放在人员列右侧。"
            )

    def _scan_people(self) -> None:
        self._rows.clear()
        self.duplicate_people.clear()
        for row in range(self._header_row + 1, self._summary.max_row + 1):
            name = normalize_name(self._summary.cell(row=row, column=1).value)
            if not name:
                continue
            if name in self._rows:
                self.duplicate_people.append(name)
                continue
            self._rows[name] = row

    def _scan_projects(self) -> List[str]:
        """读「项目号」台账表（若有）；自动跳过表头关键字。"""
        sheet = self._wb[SHEET_PROJECTS] if SHEET_PROJECTS in self._wb.sheetnames else None
        if sheet is None:
            return []
        result: List[str] = []
        for row in sheet.iter_rows(min_col=1, max_col=1, values_only=True):
            value = row[0] if row else None
            pid = normalize_project_id(value)
            if not pid or pid in {"项目号", "项目编号", "项目"}:
                continue
            if pid not in result:
                result.append(pid)
        return result

    def _build_detail_index(self) -> None:
        self._assigned_at.clear()
        if self._detail is None:
            return
        for row in self._detail.iter_rows(min_row=2, values_only=True):
            if not row or len(row) < 4:
                continue
            key = parse_month_key(row[0])
            name = normalize_name(row[1])
            action = normalize_name(row[3])
            when = row[5] if len(row) > 5 else ""
            if key is None or not name:
                continue
            if action == ACTION_REVOKE:
                self._assigned_at.pop((key, name), None)
            else:
                self._assigned_at[(key, name)] = str(when or "")

    # ------------------------------------------------------------------ 查询
    def month_keys(self) -> List[MonthKey]:
        return sorted(self._columns)

    def years(self) -> List[int]:
        return sorted({year for year, _ in self._columns})

    def people(self) -> List[str]:
        return list(self._rows)

    def projects_of(self, key: MonthKey, person: str) -> List[str]:
        """该人该月已有的项目号列表；没有返回空列表。"""
        column = self._columns.get(key)
        row = self._rows.get(person)
        if column is None or row is None:
            return []
        return split_projects(self._summary.cell(row=row, column=column).value)

    def has_project(self, key: MonthKey, person: str, project_id: str) -> bool:
        return normalize_project_id(project_id) in self.projects_of(key, person)

    def assigned_at(self, key: MonthKey, person: str) -> str:
        return self._assigned_at.get((key, person), "")

    def who_has(self, key: MonthKey, project_id: str) -> List[str]:
        """本月里已经占用了该项目号的人员（用于「同号不同人」的软提示）。"""
        target = normalize_project_id(project_id)
        if not target:
            return []
        return [name for name in self._rows if target in self.projects_of(key, name)]

    def lookup(self, project_id: str) -> List[Tuple[MonthKey, str, str]]:
        """按项目号反查：返回 [(月份, 人员, 项目号)]。"""
        target = normalize_project_id(project_id)
        if not target:
            return []
        hits: List[Tuple[MonthKey, str, str]] = []
        for key in self._columns:
            for name in self._rows:
                if target in self.projects_of(key, name):
                    hits.append((key, name, target))
        return hits

    # ------------------------------------------------------------------ 检索
    def all_assignments(self) -> List[Tuple[MonthKey, str, str]]:
        """全表所有分配记录：[(月份, 人员, 项目号)]，按月份顺序。"""
        rows: List[Tuple[MonthKey, str, str]] = []
        for key in self.month_keys():
            for name in self._rows:
                for project in self.projects_of(key, name):
                    rows.append((key, name, project))
        return rows

    def search_by_person(self, person: str) -> List[Tuple[MonthKey, str, str, str]]:
        """按人员检索：返回该人所有月份的分配 [(月份, 人员, 项目号, 分配时间)]。"""
        target = normalize_name(person)
        if not target:
            return []
        rows: List[Tuple[MonthKey, str, str, str]] = []
        for key, name, project in self.all_assignments():
            if name == target:
                rows.append((key, name, project, self.assigned_at(key, name)))
        return rows

    def search_by_project(self, project_id: str) -> List[Tuple[MonthKey, str, str, str]]:
        """按项目号检索（一字不差）：返回该号出现的所有记录。"""
        target = normalize_project_id(project_id)
        if not target:
            return []
        rows: List[Tuple[MonthKey, str, str, str]] = []
        for key, name, project in self.all_assignments():
            if project == target:
                rows.append((key, name, project, self.assigned_at(key, name)))
        return rows

    def all_project_ids(self) -> List[str]:
        """项目号台账 + 分配格里的全部项目号（去重、按字符串排序），用于下拉候选。"""
        found = set(self._projects)
        for column in self._columns.values():
            for row in self._rows.values():
                for project in split_projects(
                    self._summary.cell(row=row, column=column).value
                ):
                    found.add(project)
        return sorted(found)

    def search_people(self, text: str) -> List[Tuple[MonthKey, str, str, str]]:
        """按人员模糊检索：姓名里包含该文本的所有人，全部月份的记录。"""
        target = normalize_name(text)
        if not target:
            return []
        matched = {name for name in self._rows if target in name}
        if not matched:
            return []
        rows: List[Tuple[MonthKey, str, str, str]] = []
        for key, name, project in self.all_assignments():
            if name in matched:
                rows.append((key, name, project, self.assigned_at(key, name)))
        return rows

    # ------------------------------------------------------------------ 月份列
    def ensure_month_column(self, key: MonthKey) -> MonthKey:
        """确保汇总表里有该月份列；没有就在正确位置新建一列（复制样式）。"""
        if key in self._columns:
            return key

        ordered = sorted(self._columns)
        insert_at = 2  # 月份列从第 2 列开始
        for existing in ordered:
            if existing > key:
                break
            insert_at += 1

        worksheet = self._summary

        # openpyxl 的 insert_cols 不会搬动合并单元格：先拆掉受影响的合并区，插入后按新位置重新合并
        affected_merges = []
        for merged in list(worksheet.merged_cells.ranges):
            if merged.max_col < insert_at:
                continue
            worksheet.merged_cells.ranges.remove(merged)
            if merged.min_col >= insert_at:
                affected_merges.append(
                    (merged.min_row, merged.min_col + 1, merged.max_row, merged.max_col + 1)
                )
            else:
                affected_merges.append(
                    (merged.min_row, merged.min_col, merged.max_row, merged.max_col + 1)
                )

        worksheet.insert_cols(insert_at)

        template_col = self._columns[ordered[0]] if ordered else None
        if template_col is not None and template_col >= insert_at:
            template_col += 1  # 插入后原有列整体右移一列

        # 原表月份表头是「日期 + 自定义格式」时，新列也写成日期，保持一致
        header_value = month_label(key)
        if template_col is not None:
            template_header = worksheet.cell(row=self._header_row, column=template_col)
            if isinstance(template_header.value, (datetime, date)):
                header_value = datetime(key[0], key[1], 1)
        header = worksheet.cell(row=self._header_row, column=insert_at, value=header_value)

        if template_col is not None:
            self._clone_style(worksheet.cell(row=self._header_row, column=template_col), header)
            for row in self._rows.values():
                data_cell = worksheet.cell(row=row, column=insert_at)
                self._clone_style(worksheet.cell(row=row, column=template_col), data_cell)
                data_cell.number_format = "@"
        else:
            header.font = Font(bold=True)
            for row in self._rows.values():
                worksheet.cell(row=row, column=insert_at).number_format = "@"

        for min_row, min_col, max_row, max_col in affected_merges:
            worksheet.merge_cells(
                start_row=min_row, start_column=min_col, end_row=max_row, end_column=max_col
            )

        self._scan_month_columns()
        return key

    @staticmethod
    def _clone_style(source, target) -> None:
        try:
            if source.has_style:
                target._style = _copy(source._style)
        except Exception:
            pass  # 样式复制失败不影响功能，最多是格式没那么整齐

    # ------------------------------------------------------------------ 写入
    def assign(self, key: MonthKey, person: str, project_id) -> str:
        """分配项目号。成功返回写入的项目号，失败抛 AssignError。"""
        if person not in self._rows:
            raise AssignError(f"汇总表里没有「{person}」这个人。")
        if person in self.duplicate_people:
            raise AssignError(f"汇总表里「{person}」有重名行，请先手工处理。")

        project = normalize_project_id(project_id)
        if not project:
            raise AssignError("项目号不能为空。")
        if len(project) > 40:
            raise AssignError("项目号太长（超过 40 个字符）。")

        if key in self._columns and project in self.projects_of(key, person):
            raise AssignError(
                f"{person} · {month_label(key)} 已分配过项目号「{project}」，不能重复分配。"
            )

        self.ensure_month_column(key)
        existing = self.projects_of(key, person)
        new_list = existing + [project]

        self._backup()
        cell = self._summary.cell(row=self._rows[person], column=self._columns[key])
        previous_value = cell.value
        previous_format = cell.number_format
        cell.value = join_projects(new_list)
        cell.number_format = "@"  # 文本格式，防止前导零被吃掉
        self._apply_duplicate_highlight()
        self._autofit_summary()
        detail_row = self._append_detail(key, person, project, ACTION_ASSIGN)
        try:
            self._save_atomic()
        except AssignError:
            cell.value = previous_value
            cell.number_format = previous_format
            self._drop_detail_row(detail_row)
            self._build_detail_index()
            self._apply_duplicate_highlight()
            raise
        self._build_detail_index()
        return project

    def replace_project(self, key: MonthKey, person: str, old_id, new_id) -> str:
        """把某人的某个项目号改成另一个。成功返回新的项目号，失败抛 AssignError。"""
        if person not in self._rows:
            raise AssignError(f"汇总表里没有「{person}」这个人。")
        if person in self.duplicate_people:
            raise AssignError(f"汇总表里「{person}」有重名行，请先手工处理。")

        old = normalize_project_id(old_id)
        new = normalize_project_id(new_id)
        if not old:
            raise AssignError("请先选择要修改的原项目号。")
        if not new:
            raise AssignError("新的项目号不能为空。")
        if len(new) > 40:
            raise AssignError("项目号太长（超过 40 个字符）。")

        existing = self.projects_of(key, person)
        if old not in existing:
            raise AssignError(f"{person} · {month_label(key)} 没有项目号「{old}」，无法修改。")
        if new in existing and new != old:
            raise AssignError(f"{person} · {month_label(key)} 已分配过「{new}」，不能重复。")
        if new == old:
            raise AssignError("新旧项目号相同，无需修改。")

        new_list = [new if item == old else item for item in existing]

        self._backup()
        cell = self._summary.cell(row=self._rows[person], column=self._columns[key])
        previous_value = cell.value
        previous_format = cell.number_format
        cell.value = join_projects(new_list)
        cell.number_format = "@"
        self._apply_duplicate_highlight()
        self._autofit_summary()
        detail_row = self._append_detail(key, person, new, ACTION_MODIFY, old_value=old)
        try:
            self._save_atomic()
        except AssignError:
            cell.value = previous_value
            cell.number_format = previous_format
            self._drop_detail_row(detail_row)
            self._build_detail_index()
            self._apply_duplicate_highlight()
            raise
        self._build_detail_index()
        return new

    def add_person(self, name) -> str:
        """在 A 列第一个空行里加入一个人员（模板通常预留了空行）。"""
        return self.add_people([name])[0]

    def add_people(self, names) -> List[str]:
        """批量新增人员：只备份一次、只保存一次。"""
        prepared: List[str] = []
        for raw in names:
            person = normalize_name(raw)
            if not person:
                continue
            if person in self._rows:
                raise AssignError(f"「{person}」已经在表里了。")
            if person in self.duplicate_people:
                raise AssignError(f"「{person}」有重名行，请先手工处理。")
            if person in prepared:
                raise AssignError(f"「{person}」重复了。")
            prepared.append(person)
        if not prepared:
            raise AssignError("没有可添加的姓名。")

        self._backup()
        written = []
        for person in prepared:
            row = self._next_empty_person_row()
            cell = self._summary.cell(row=row, column=1)
            written.append((cell, cell.value))
            self._fill_person_row(row, person)

        self._autofit_summary()
        try:
            self._save_atomic()
        except AssignError:
            for cell, previous in written:
                cell.value = previous
            raise
        self._scan_people()
        return prepared

    def add_project(self, project_id) -> str:
        """往「项目号」台账表里加一个项目号（含去重、原子保存）。"""
        project = normalize_project_id(project_id)
        if not project:
            raise AssignError("项目号不能为空。")
        if len(project) > 40:
            raise AssignError("项目号太长（超过 40 个字符）。")
        if project in self.all_project_ids():
            raise AssignError(f"项目号「{project}」已存在。")

        sheet = self._wb[SHEET_PROJECTS] if SHEET_PROJECTS in self._wb.sheetnames else None
        self._backup()
        if sheet is None:
            sheet = self._wb.create_sheet(SHEET_PROJECTS)
            sheet.cell(row=1, column=1, value="项目号").font = Font(bold=True)
            next_row = 2
        else:
            next_row = sheet.max_row + 1
        cell = sheet.cell(row=next_row, column=1, value=project)
        cell.number_format = "@"
        try:
            self._save_atomic()
        except AssignError:
            cell.value = None
            raise
        self._projects = self._scan_projects()
        return project

    def _next_empty_person_row(self) -> int:
        """A 列第一个"姓名空、且该行没有数据"的行号。"""
        for row in range(self._header_row + 1, self._summary.max_row + 1):
            if normalize_name(self._summary.cell(row=row, column=1).value):
                continue
            has_data = any(
                self._summary.cell(row=row, column=column).value not in (None, "")
                for column in self._columns.values()
            )
            if not has_data:
                return row
        return self._summary.max_row + 1

    def _fill_person_row(self, row: int, person: str) -> None:
        """写姓名；若是新追加的行，复制上一行的样式与行高。"""
        cell = self._summary.cell(row=row, column=1)
        if row > self._summary.max_row:
            source_row = row - 1
            if source_row > self._header_row:
                self._clone_style(self._summary.cell(row=source_row, column=1), cell)
                height = self._summary.row_dimensions[source_row].height
                if height:
                    self._summary.row_dimensions[row].height = height
                for column in self._columns.values():
                    self._clone_style(
                        self._summary.cell(row=source_row, column=column),
                        self._summary.cell(row=row, column=column),
                    )
        cell.value = person

    def _append_detail(
        self, key: MonthKey, person: str, project: str, action: str, old_value: str = ""
    ) -> int:
        """追加一条明细，返回写入的行号（用于保存失败时回滚）。"""
        if self._detail is None:
            self._detail = self._wb.create_sheet(SHEET_DETAIL)
        sheet = self._detail
        for index, title in enumerate(DETAIL_HEADER, start=1):
            header = sheet.cell(row=1, column=index)
            if header.value is None:
                header.value = title
        next_row = sheet.max_row + 1
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        values = (month_label(key), person, project, action, old_value, stamp)
        for index, value in enumerate(values, start=1):
            cell = sheet.cell(row=next_row, column=index, value=value)
            if index in (3, 5):  # 项目号、原项目号都按文本存
                cell.number_format = "@"
        return next_row

    def _drop_detail_row(self, row: int) -> None:
        if self._detail is None or row < 2 or row > self._detail.max_row:
            return
        self._detail.delete_rows(row, 1)

    # ------------------------------------------------------------------ 高亮
    @staticmethod
    def _is_highlighted(cell) -> bool:
        fill = cell.fill
        if fill is None or fill.fill_type is None:
            return False
        rgb = getattr(fill.fgColor, "rgb", None)
        return isinstance(rgb, str) and rgb.endswith("FFF3CD")

    def _apply_duplicate_highlight(self) -> None:
        """同一个月里出现多次的项目号，其所在格子标黄；先清除旧高亮再重算。"""
        # 1) 清除旧高亮（按颜色识别，不碰用户自己的其它填充色）
        for key, column in self._columns.items():
            for row in self._rows.values():
                cell = self._summary.cell(row=row, column=column)
                if self._is_highlighted(cell):
                    cell.fill = PatternFill(fill_type=None)
        # 2) 统计每个月份里各项目号出现次数
        for key, column in self._columns.items():
            counter: Counter = Counter()
            for row in self._rows.values():
                for project in split_projects(
                    self._summary.cell(row=row, column=column).value
                ):
                    counter[project] += 1
            # 3) 出现多于一次的项目号 → 高亮所在格子
            for row in self._rows.values():
                cell = self._summary.cell(row=row, column=column)
                if any(counter[project] > 1 for project in split_projects(cell.value)):
                    cell.fill = HIGHLIGHT_FILL

    # ------------------------------------------------------------------ 自适应列宽
    @staticmethod
    def _display_len(text) -> int:
        total = 0
        for ch in str(text or ""):
            total += 2 if ord(ch) > 127 else 1
        return total

    @staticmethod
    def _set_width(worksheet, letter: str, width: float) -> None:
        """只加宽、不压窄 —— 保留模板原有的列宽。"""
        dimension = worksheet.column_dimensions[letter]
        current = dimension.width or 0.0
        if width > current:
            dimension.width = width

    def _autofit_summary(self) -> None:
        """按内容自适应列宽（只加宽，不压窄；中文按 2 个字符计）。"""
        worksheet = self._summary

        max_name = max((self._display_len(name) for name in self._rows), default=0)
        self._set_width(worksheet, "A", max(8, max_name + 4))

        for key, column in self._columns.items():
            letter = get_column_letter(column)
            best = self._display_len(month_label(key)) + 2
            for row in self._rows.values():
                value = worksheet.cell(row=row, column=column).value
                if value:
                    best = max(best, self._display_len(value) + 2)
            self._set_width(worksheet, letter, min(best, 60))

    # ------------------------------------------------------------------ 备份/保存
    def _backup(self) -> None:
        if not self.path.is_file():
            return
        folder = self.path.parent / "backup"
        folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target = folder / f"{self.path.stem}_{stamp}{self.path.suffix}"
        try:
            shutil.copy2(self.path, target)
        except OSError:
            pass  # 备份失败不阻断写入，但下面保存仍会报错

    def _save_atomic(self) -> None:
        temporary = self.path.with_name(self.path.name + ".tmp")
        try:
            self._wb.save(temporary)
            os.replace(temporary, self.path)
        except PermissionError as error:
            if temporary.exists():
                temporary.unlink(missing_ok=True)
            raise AssignError(
                "Excel 正被占用（可能正开着这个文件），请先关闭后重试。"
            ) from error
        finally:
            if temporary.exists():
                temporary.unlink(missing_ok=True)
        self.last_saved = datetime.now().strftime("%H:%M:%S")
