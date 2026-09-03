"""两个仿真共享的配置与输出数据结构。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from stk_simulation.infrastructure.paths import application_root


@dataclass
class PathsConfig:
    repo_root: Path
    data_dir: Path
    result_dir: Path

    @classmethod
    def for_simulation(cls, name: str) -> "PathsConfig":
        root = application_root()
        return cls(root, root / "data", root / "results" / name)


@dataclass
class STKConfig:
    mode: str = "new"


@dataclass
class ScenarioConfig:
    name: str
    start_time: str = "1 Sep 2026 00:00:00.000"
    stop_time: str = "2 Sep 2026 00:00:00.000"


@dataclass
class SatelliteConfig:
    name: str
    ssc: int
    step: float
    tle_file: Path
    tle_url: str = ""


@dataclass
class NamedConfig:
    name: str


@dataclass
class OutputConfig:
    image_name: str = ""


@dataclass
class OutputResult:
    result_dir: Path
    image_name: str
    image_path: Path


def current_local_day_period() -> tuple[str, str]:
    """按电脑本地日期生成当天 00:00 至次日 00:00 的 UTCG 文本。"""
    start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    stop = start + timedelta(days=1)
    return _stk_time(start), _stk_time(stop)


def _stk_time(value: datetime) -> str:
    months = (
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
    )
    return (
        f"{value.day} {months[value.month - 1]} {value.year} "
        f"{value:%H:%M:%S}.000"
    )
