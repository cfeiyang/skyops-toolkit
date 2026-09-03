"""两个仿真共享的配置与输出数据结构。"""

from __future__ import annotations

from dataclasses import dataclass
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
