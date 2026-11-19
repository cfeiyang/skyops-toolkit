"""STK 12 Connect command recipes, usable without STK or Qt."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import PureWindowsPath
import math
import re

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
PROPAGATORS = ("TwoBody", "J2Perturbation", "J4Perturbation")
FRAMES = ("J2000", "ICRF")
UNITS = "Units_SetConnect / Default"


@dataclass(frozen=True)
class Plan:
    commands: tuple[str, ...]
    inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()
    requires_scenario: bool = True


def name(text, label):
    value = text.strip()
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", value):
        raise ValueError(f"{label}须以英文字母开头，最多 64 个英文字母、数字或下划线。")
    return value


def path_arg(text, label, suffixes):
    value = text.strip()
    path = PureWindowsPath(value)
    if not path.is_absolute() or path.suffix.lower() not in suffixes:
        raise ValueError(f"{label}须为 Windows 绝对路径，扩展名为 {' / '.join(suffixes)}。")
    if value.startswith(("\\\\?\\", "\\\\.\\")) or any(c in value for c in '"\r\n;<>|*?'):
        raise ValueError(f"{label}包含 Connect 无法可靠处理的字符。")
    return str(path)


def utc_text(value: datetime) -> str:
    return f'{value.day} {MONTHS[value.month - 1]} {value.year} {value:%H:%M:%S}.{value.microsecond // 1000:03d}'


def number(value):
    if not math.isfinite(value):
        raise ValueError("请输入有效数值。")
    return f"{value:.9f}".rstrip("0").rstrip(".")


def scenario(scenario_name, start, stop):
    scenario_name = name(scenario_name, "场景名")
    if start >= stop:
        raise ValueError("结束时间须晚于开始时间。")
    return Plan((f"New / Scenario {scenario_name} CentralBody Earth", UNITS,
                 f'SetAnalysisTimePeriod * "{utc_text(start)}" "{utc_text(stop)}"',
                 "SetEpoch * UseAnalysisStartTime"), requires_scenario=False)


def open_scenario(file):
    file = path_arg(file, "场景文件", (".sc", ".vdf"))
    if PureWindowsPath(file).suffix.lower() == ".vdf":
        cmd = f'Load / VDF "{file}"'
    else:
        cmd = f'Load / Scenario "{file}"'
    return Plan((cmd,), inputs=(file,), requires_scenario=False)


def save_scenario():
    return Plan(("Save / *",))


def satellite(sat, mode, create, *, propagator="", frame="", step=60, a_km=0,
              e=0, inc=0, arg=0, raan=0, mean=0, file="", tle1="", tle2=""):
    sat = name(sat, "卫星名")
    target = f"*/Satellite/{sat}"
    commands = [f"New / */Satellite {sat} CentralBody Earth NoDefault"] if create else []
    if mode == "classical":
        if propagator not in PROPAGATORS or frame not in FRAMES:
            raise ValueError("请选择支持的传播器和参考系。")
        if not (0 <= e < 1 and 0 <= inc <= 180 and step >= 0.001):
            raise ValueError("偏心率须在 [0, 1)，倾角须在 [0°, 180°]，步长至少 0.001 秒。")
        if a_km * (1 - e) <= 6378.137:
            raise ValueError("近地点半径 a × (1 − e) 须大于地球赤道半径 6378.137 km。")
        commands += [UNITS, f'SetState {target} Classical {propagator} '
                     f'UseScenarioInterval {number(step)} {frame} "UseAnalysisStartTime" '
                     + " ".join(number(v) for v in (a_km * 1000, e, inc, arg % 360, raan % 360, mean % 360))]
        return Plan(tuple(commands))
    if mode == "ephemeris":
        file = path_arg(file, "星历文件", (".e", ".be", ".oem"))
        file_format = " FileFormat CCSDS_OEM" if PureWindowsPath(file).suffix.lower() == ".oem" else ""
        return Plan(tuple(commands + [f'SetState {target} FromFile "{file}"{file_format}']), inputs=(file,))
    if mode == "tle":
        line1, line2 = tle1.strip(), tle2.strip()
        if (len(line1) != 69 or len(line2) != 69 or not line1.startswith("1 ")
                or not line2.startswith("2 ") or line1[2:7] != line2[2:7]
                or not all(re.fullmatch(r"[A-Z0-9.+ -]+", line) for line in (line1, line2))):
            raise ValueError("请输入同一颗卫星的两行标准 TLE，每行 69 个字符，并保留行内空格。")
        return Plan(tuple(commands + [UNITS, f'SetState {target} TLE "{line1}" "{line2}" '
                                      'TimePeriod UseScenarioInterval']))
    raise ValueError("请选择轨道来源。")


def export_ephemeris(sat, file):
    target = f"*/Satellite/{name(sat, '卫星名')}"
    file = path_arg(file, "导出路径", (".e", ".oem"))
    kind = "STK" if PureWindowsPath(file).suffix.lower() == ".e" else "CCSDS"
    return Plan((f'ExportDataFile {target} Ephemeris "{file}" Type {kind} CoordSys J2000',),
                outputs=(file,))


def station(station_name, lat, lon, create, *, elevation, gso):
    station_name = name(station_name, "地面站名")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("纬度须在 −90° 至 90°，经度须在 −180° 至 180°。")
    if not -90 <= elevation <= 90:
        raise ValueError("最低仰角须在 −90° 至 90°。")
    if not 0 <= gso <= 180:
        raise ValueError("GSO 隔离角须在 0° 至 180°。")
    target = f"*/Facility/{station_name}"
    commands = [f"New / */Facility {station_name} CentralBody Earth NoDefault"] if create else []
    commands += [
        UNITS,
        f"SetPosition {target} Geodetic {number(lat)} {number(lon)} 0",
        f"SetConstraint {target} ElevationAngle Min {number(elevation)} IncludeIntervals",
        f"SetConstraint {target} GeoExclusion {number(gso)} IncludeIntervals",
    ]
    return Plan(tuple(commands))


def access(sat, station_name):
    sat = name(sat, "卫星名")
    station_name = name(station_name, "地面站名")
    return Plan((f"Access */Facility/{station_name} */Satellite/{sat} "
                 "TimePeriod UseScenarioInterval AutoAddTimeline On",))
