"""Excel 存储与检索：样式克隆、并发控制、安全追加和历史读取。"""

import os
import tempfile
from contextlib import contextmanager
from copy import copy
from datetime import date, datetime, time
from pathlib import Path
from threading import RLock
from typing import Any, Dict, Iterator, List, Mapping, Optional, Tuple

import pandas as pd

from openpyxl import load_workbook
from openpyxl.cell.cell import MergedCell
from openpyxl.worksheet.worksheet import Worksheet

from app.config import COL_MAP, OPTIONSfrom app.paths import DATA_DIR

EXCEL_PATH = DATA_DIR / OPTIONS["Excel文件名"]
PERMISSION_MESSAGE = "Excel 正被打开占用，请先关闭表格再点击保存！"


_PROCESS_LOCK = RLock()


def get_process_lock() -> Any:
    """进程级共享线程锁，防止多人同时保存丢失记录。"""
    return _PROCESS_LOCK


@contextmanager
def excel_access(write: bool = False) -> Iterator[None]:
    """串行读写；独占锁文件额外防止多个 SkyOps 进程同时追加。"""
    lock_path = EXCEL_PATH.with_name(EXCEL_PATH.name + ".skyops.lock")
    with get_process_lock():
        acquired = False
        try:
            if write:
                try:
                    descriptor = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                except FileExistsError as exc:
                    raise RuntimeError(
                        "其他会话正在保存，请稍后重试。若应用曾异常退出，"
                        "请管理员确认没有写入进程后删除同目录的 .skyops.lock 文件。"
                    ) from exc
                acquired = True
                os.close(descriptor)
            yield
        finally:
            if acquired:
                lock_path.unlink(missing_ok=True)


def calculate_duration(
    start_time: time, end_time: time, interruption_minutes: int
) -> Tuple[int, int]:
    """计算总分钟数和有效分钟数；结束时间较早表示跨午夜。"""
    if (
        isinstance(interruption_minutes, bool)
        or not isinstance(interruption_minutes, int)
        or interruption_minutes < 0
    ):
        raise ValueError("中断时长必须是非负整数分钟。")
    duration = (end_time.hour * 60 + end_time.minute) - (start_time.hour * 60 + start_time.minute)
    if duration < 0:
        duration += 24 * 60
    if interruption_minutes > duration:
        raise ValueError("中断时长不能超过测试时长。")
    return duration, duration - interruption_minutes


def clone_row_style(worksheet: Worksheet, source_row: int, target_row: int) -> None:
    """完整克隆字体、字号、边框、填充、对齐、数字格式、保护及行高。"""
    for column in range(1, max(worksheet.max_column, max(COL_MAP.values())) + 1):
        source = worksheet.cell(source_row, column)
        target = worksheet.cell(target_row, column)
        if isinstance(target, MergedCell):
            raise ValueError("待写入行包含合并单元格，请检查 Excel 数据区域。")
        # _style 同时保留未单独列举的单元格样式属性，不复制业务内容。
        target._style = copy(source._style)
        target.font = copy(source.font)
        target.fill = copy(source.fill)
        target.border = copy(source.border)
        target.alignment = copy(source.alignment)
        target.number_format = source.number_format
        target.protection = copy(source.protection)
    if source_row in worksheet.row_dimensions:
        dimension = copy(worksheet.row_dimensions[source_row])
        dimension.index = target_row
        worksheet.row_dimensions[target_row] = dimension


def get_worksheet(workbook: Any) -> Worksheet:
    """选择绑定工作表，避免依赖 Excel 上次保存时的活动页。"""
    sheet_name = OPTIONS["工作表名称"]
    if sheet_name:
        if sheet_name not in workbook.sheetnames:
            raise ValueError(f"找不到配置的工作表：{sheet_name}")
        worksheet = workbook[sheet_name]
    else:
        worksheet = workbook.worksheets[0]
    if not isinstance(worksheet, Worksheet):
        raise ValueError("绑定的工作表不是普通数据工作表。")
    return worksheet


def has_content(value: Any) -> bool:
    """忽略空值及纯空白字符串。"""
    return value is not None and (not isinstance(value, str) or bool(value.strip()))


def get_data_rows(worksheet: Worksheet) -> List[int]:
    """定位真实业务行，排除第三行说明及仅带样式的空白尾行。"""
    return [
        row[0].row
        for row in worksheet.iter_rows(
            min_row=OPTIONS["数据起始行"], max_row=worksheet.max_row,
            max_col=max(COL_MAP.values()),
        )
        if any(has_content(cell.value) for cell in row)
    ]


def parse_record_date(value: Any) -> date:
    """接受日期对象、YYYY/M/D 或旧版 YYYY-MM-DD，并校验真实日期。"""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for pattern in ("%Y/%m/%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    raise ValueError("测试日期必须是有效日期，例如 2026/10/10。")


def format_record_date(value: Any) -> str:
    """统一显示为 YYYY/M/D，仅转换显示，不改写历史数据。"""
    if not has_content(value):
        return "未填写"
    try:
        parsed = parse_record_date(value)
        return f"{parsed.year}/{parsed.month}/{parsed.day}"
    except ValueError:
        return str(value).strip()


def file_signature() -> Tuple[int, int]:
    """检测保存过程中外部程序修改原文件的情况。"""
    status = EXCEL_PATH.stat()
    return status.st_mtime_ns, status.st_size


def get_excel_status() -> Dict[str, Any]:
    """返回文件存在状态、记录数、最新一条业务记录日期及读取错误。"""
    result = {"exists": EXCEL_PATH.is_file(), "count": 0, "latest_date": "暂无记录", "error": ""}
    if not result["exists"]:
        return result
    workbook = None
    try:
        with excel_access():
            workbook = load_workbook(EXCEL_PATH, data_only=False)
            worksheet = get_worksheet(workbook)
            rows = get_data_rows(worksheet)
            result["count"] = len(rows)
            if rows:
                result["latest_date"] = format_record_date(
                    worksheet.cell(rows[-1], COL_MAP["测试日期"]).value
                )
    except PermissionError:
        result["error"] = PERMISSION_MESSAGE
    except Exception as exc:
        result["error"] = f"读取 Excel 状态失败：{exc}"
    finally:
        if workbook is not None:
            workbook.close()
    return result


class RecordValidationError(ValueError):
    """带字段归属的校验错误，界面据此跳转到对应录入分区。"""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field
        self.message = message


def validate_record(record: Mapping[str, Any]) -> None:
    """保存前再次校验必填内容及分钟数关系。"""
    for field in ("测试日期", "测试地点", "测试情况"):
        if not has_content(record.get(field)):
            raise RecordValidationError(field, f"请填写{field}。")
    parse_record_date(record["测试日期"])
    for field in ("测试时长", "有效时长"):
        value = record.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise RecordValidationError(field, f"{field}必须是非负整数。")
    interruption = record.get("中断时长")
    if interruption == "无":
        interruption = 0
    if isinstance(interruption, bool) or not isinstance(interruption, int) or interruption < 0:
        raise RecordValidationError("中断时长", "中断时长必须是非负整数或“无”。")
    if record["测试时长"] - interruption != record["有效时长"]:
        raise RecordValidationError("有效时长", "测试时长、中断时长与有效时长不一致。")


def append_record_to_excel(record: Mapping[str, Any]) -> Tuple[bool, str]:
    """复制尾行样式后追加，先写同目录临时文件，再原子替换目标文件。"""
    workbook = None
    temporary_path: Optional[Path] = None
    try:
        validate_record(record)
        with excel_access(write=True):
            if not EXCEL_PATH.is_file():
                return False, f"未找到 data/{EXCEL_PATH.name}，请检查数据目录。"
            original_signature = file_signature()
            workbook = load_workbook(EXCEL_PATH, data_only=False)
            worksheet = get_worksheet(workbook)
            rows = get_data_rows(worksheet)
            if rows:
                source_row = rows[-1]
                target_row = source_row + 1
                previous_number = worksheet.cell(source_row, COL_MAP["序号"]).value
                if isinstance(previous_number, bool):
                    raise ValueError("上一条记录的序号无效，请检查原表。")
                try:
                    numeric_number = float(previous_number)
                    previous_integer = int(numeric_number)
                    if previous_integer < 0 or numeric_number != previous_integer:
                        raise ValueError
                except (TypeError, ValueError, OverflowError) as exc:
                    raise ValueError("上一条记录的序号不是有效整数，请检查原表后重试。") from exc
                next_number = previous_integer + 1
            else:
                target_row = OPTIONS["数据起始行"]
                # 空表优先复用已有空白首行模板，没有模板时复制紧邻上一行。
                source_row = target_row if worksheet.max_row >= target_row else target_row - 1
                next_number = 1
            clone_row_style(worksheet, source_row, target_row)
            values = dict(record)
            values["序号"] = next_number
            values["测试日期"] = parse_record_date(values["测试日期"])
            for field, column in COL_MAP.items():
                cell = worksheet.cell(target_row, column)
                value = values.get(field, "")
                cell.value = value
                # 将用户文本明确保存为文字，防止“=”开头的内容成为公式。
                if isinstance(value, str):
                    cell.data_type = "s"
            # 新日期保留为 Excel 日期类型，明确指定斜杠显示；其余样式完整继承。
            worksheet.cell(target_row, COL_MAP["测试日期"]).number_format = OPTIONS["Excel日期格式"]
            with tempfile.NamedTemporaryFile(
                prefix=".skyops-", suffix=".xlsx", dir=str(EXCEL_PATH.parent), delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
            workbook.save(temporary_path)
            workbook.close()
            workbook = None
            if file_signature() != original_signature:
                raise RuntimeError("保存期间 Excel 被其他程序修改，本次未写入。请确认表格后重新保存。")
            os.replace(str(temporary_path), str(EXCEL_PATH))
            temporary_path = None
        return True, f"保存成功！已追加第 {next_number} 条记录。"
    except PermissionError:
        return False, PERMISSION_MESSAGE
    except Exception as exc:
        return False, f"保存失败：{exc}"
    finally:
        if workbook is not None:
            workbook.close()
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass


def load_history() -> pd.DataFrame:
    """Pandas 使用第二行表头，跳过第三行说明，按物理列位置严格映射。"""
    with excel_access():
        if not EXCEL_PATH.is_file():
            raise FileNotFoundError(f"未找到 {EXCEL_PATH.name}")
        dataframe = pd.read_excel(
            EXCEL_PATH, sheet_name=OPTIONS["工作表名称"] or 0,
            header=OPTIONS["表头行"] - 1, skiprows=[OPTIONS["说明行"] - 1],
            dtype=object, engine="openpyxl", keep_default_na=False,
        )
    if dataframe.shape[1] < max(COL_MAP.values()):
        raise ValueError("Excel 列数不足，请确认原表包含完整的 15 列。")
    history = pd.DataFrame({
        field: dataframe.iloc[:, column - 1] for field, column in COL_MAP.items()
    })
    populated = history.apply(
        lambda column: column.map(lambda value: pd.notna(value) and has_content(value))
    ).any(axis=1)
    history = history.loc[populated].copy().fillna("")
    history["测试日期"] = history["测试日期"].map(format_record_date)
    for field in ("问题记录", "测试地点"):
        history[field] = history[field].astype(str).str.strip()
    return history.reset_index(drop=True)
