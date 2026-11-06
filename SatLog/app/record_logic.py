"""录入草稿与地点模板：不依赖界面控件，便于单独维护与测试。"""

from datetime import date, time
from typing import Any, Dict, Mapping, Tuple

from app.config import OPTIONS
from app.excel_service import calculate_duration


def default_draft() -> Dict[str, Any]:
    """为每个浏览器会话建立独立草稿。"""
    return {
        "test_date": date.today(),
        "experiment_name": "",
        "location_template": OPTIONS["测试地点"][0],
        "location_left": "",
        "location_right": "",
        "location_single": "",
        "start_time": time(9, 0),
        "end_time": time(10, 0),
        "interruption": 0,
        "main_station": OPTIONS["主站"][0],
        "antenna": OPTIONS["小站/天线"][0],
        "baseband": OPTIONS["基带"][0],
        "frequency_template": next(iter(OPTIONS["频点模板"])),
        "frequency_text": next(iter(OPTIONS["频点模板"].values())),
        "controller": OPTIONS["运控人员"][0],
        "participants": [],
        "parameters": "",
        "test_description": "",
        "problem_tags": [],
        "problem_description": "",
    }


def split_location(template: str) -> Tuple[str, str, str]:
    """解析原表箭头地点；自测站点仍按单地点保存。"""
    if template == OPTIONS["自定义地点选项"]:
        return "", "", ""
    arrow = OPTIONS["地点连接符"]
    if arrow in template:
        left, right = template.split(arrow, 1)
        return left.strip(), right.strip(), ""
    return "", "", template


def build_location(draft: Mapping[str, Any]) -> str:
    """将左右地点连接为与原表相同的箭头形式，不自动改写历史地点。"""
    template = draft["location_template"]
    if template != OPTIONS["自定义地点选项"] and OPTIONS["地点连接符"] not in template:
        return str(draft["location_single"]).strip()
    left = str(draft["location_left"]).strip()
    right = str(draft["location_right"]).strip()
    if not left or not right:
        return ""
    return f'{left}{OPTIONS["地点连接符"]}{right}'


def build_record(draft: Mapping[str, Any]) -> Dict[str, Any]:
    """从草稿组装严格对应 15 列的记录，日期保持原生日期对象。"""
    duration, effective = calculate_duration(
        draft["start_time"], draft["end_time"], int(draft["interruption"])
    )
    problem = (
        "".join(f"【{tag}】" for tag in draft["problem_tags"])
        + str(draft["problem_description"]).strip()
    ) or "无"
    return {
        "测试日期": draft["test_date"],
        "试验名称": str(draft["experiment_name"]).strip(),
        "测试时间": f'{draft["start_time"]:%H:%M}~{draft["end_time"]:%H:%M}',
        "测试时长": duration,
        "中断时长": "无" if draft["interruption"] == 0 else int(draft["interruption"]),
        "有效时长": effective,
        "终端情况": (
            f'主站：{draft["main_station"]}\n小站：{draft["antenna"]}\n基带：{draft["baseband"]}'
        ),
        "频点设置": str(draft["frequency_text"]).strip(),
        "测试地点": build_location(draft),
        "运控人员": draft["controller"],
        "试验人员": "\n".join(draft["participants"]),
        "参数配置（转发器）": str(draft["parameters"]).strip(),
        "测试情况": str(draft["test_description"]).strip(),
        "问题记录": problem,
    }
