"""STK 12 Connect 命令，用于建链场景和文件操作。"""

from pathlib import Path
import math
import re

from skyops_sim.simulations.common import _stk_time, parse_stk_time


def _number(value: float) -> str:
    if not math.isfinite(value):
        raise ValueError("STK 参数须为有效数值。")
    return f"{value:.9f}".rstrip("0").rstrip(".")


def _name(text: str, label: str) -> str:
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", text):
        raise ValueError(f"{label}须以英文字母开头，最多 64 个英文字母、数字或下划线。")
    return text


def build_scene(name, config, tle, stations):
    sat = _name(config.satellite.name, "卫星名称")
    if not all(re.fullmatch(r"[A-Z0-9.+ -]{69}", line) for line in (tle.line1, tle.line2)):
        raise ValueError("STK 需要每行 69 个字符的标准 TLE。")
    start = _stk_time(parse_stk_time(config.scenario.start_time))
    stop = _stk_time(parse_stk_time(config.scenario.stop_time))
    target = f"*/Satellite/{sat}"
    commands = [
        f"New / Scenario {_name(name, '场景名称')} CentralBody Earth",
        "Units_SetConnect / Default",
        f'SetAnalysisTimePeriod * "{start}" "{stop}"',
        "SetEpoch * UseAnalysisStartTime",
        f"New / */Satellite {sat} CentralBody Earth NoDefault",
        f'SetState {target} TLE "{tle.line1}" "{tle.line2}" TimePeriod UseScenarioInterval '
        f"TimeStep {_number(config.satellite.step)}",
    ]
    facilities = []
    for index, station in enumerate(stations, 1):
        facility = f"*/Facility/Station_{index}"
        facilities.append(facility.removeprefix("*/"))
        if not (-90 <= station.latitude_deg <= 90 and -180 <= station.longitude_deg <= 180):
            raise ValueError(f"站点 {station.name} 的经纬度超出范围。")
        if not (-90 <= station.min_elevation_deg <= 90 and 0 <= station.gso_avoid_deg <= 180):
            raise ValueError(f"站点 {station.name} 的角度约束超出范围。")
        gso = _number(station.gso_avoid_deg) if station.gso_avoid_deg > 0 else "Off"
        commands.extend((
            f"New / */Facility Station_{index} CentralBody Earth NoDefault",
            f"SetPosition {facility} Geodetic {_number(station.latitude_deg)} "
            f"{_number(station.longitude_deg)} {_number(station.altitude_m)}",
            f"SetConstraint {facility} ElevationAngle Min {_number(station.min_elevation_deg)} IncludeIntervals",
            f"SetConstraint {facility} GeoExclusion {gso}",
        ))
    return commands, target.removeprefix("*/"), facilities


def file_command(action: str, satellite: str, path: str) -> str:
    destination = Path(path)
    suffix = {"save": ".sc", "ephemeris": ".e"}[action]
    if not destination.is_absolute() or destination.suffix.lower() != suffix:
        raise ValueError(f"请选择扩展名为 {suffix} 的绝对路径。")
    if any(c in str(destination) for c in '"\r\n;<>|*?'):
        raise ValueError("路径包含 STK Connect 不支持的字符。")
    if not destination.parent.is_dir():
        raise FileNotFoundError(f"文件夹不存在：{destination.parent}")
    if destination.exists():
        raise FileExistsError(f"文件已存在，请选择新文件名：{destination.name}")
    if action == "save":
        return f'SaveAs / * "{destination.with_suffix("")}"'
    return f'ExportDataFile */Satellite/{_name(satellite, "卫星名称")} Ephemeris "{destination}" Type STK CoordSys J2000'
