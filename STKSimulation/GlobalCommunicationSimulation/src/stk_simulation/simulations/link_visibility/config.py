"""星地建链与 AER 预报配置及标准化结果模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Tuple

from stk_simulation.simulations.common import (
    OutputResult,
    PathsConfig,
    STKConfig,
    SatelliteConfig,
    ScenarioConfig,
    current_local_day_period,
)


@dataclass
class LinkStationConfig:
    name: str = "上海临港站"
    latitude_deg: float = 30.903611
    longitude_deg: float = 121.919444
    altitude_m: float = 0.0
    min_elevation_deg: float = 15.0
    mask: Tuple[Tuple[float, float, float], ...] = ()
    gso_avoid_deg: float = 15.0


@dataclass(frozen=True)
class AccessWindow:
    access_number: int
    start_time: str
    stop_time: str
    duration_sec: float
    max_elevation_deg: float
    max_elevation_time: str


@dataclass(frozen=True)
class AERRecord:
    access_number: int
    station_name: str
    time: str
    azimuth_deg: float
    elevation_deg: float
    range_km: float


@dataclass(frozen=True)
class TrackPoint:
    time: str
    latitude_deg: float
    longitude_deg: float
    elevation_deg: float = 0.0
    linked: bool = False           # 两地同时通信（comm）
    el1: float = 0.0
    linked1: bool = False
    el2: float = 0.0
    linked2: bool = False


@dataclass
class LinkVisibilityConfig:
    paths: PathsConfig
    stk: STKConfig
    scenario: ScenarioConfig
    satellite: SatelliteConfig
    stations: list[LinkStationConfig]
    coarse_step_sec: float = 30.0
    refine_step_sec: float = 1.0
    sample_step_sec: float = 30.0
    dual_station_sync: bool = False  # False=单站建链, True=两地同时可见中继建链
    tle_file: str = ""               # 可选：本地 TLE 文件路径，优先于在线获取


@dataclass
class EngineDiffItem:
    access_number: int
    stk_start: str
    py_start: str
    start_diff_sec: float
    stk_stop: str
    py_stop: str
    stop_diff_sec: float
    max_el_diff_deg: float


@dataclass
class LinkVisibilityResult:
    engine_used: str  # "python" | "stk" | "compare"
    satellite_name: str
    station_names: tuple[str, ...]
    start_time: str
    stop_time: str
    windows: tuple[AccessWindow, ...]
    aer_records: tuple[AERRecord, ...]
    ground_track: tuple[TrackPoint, ...]
    output: OutputResult
    cfg: LinkVisibilityConfig
    diff_items: tuple[EngineDiffItem, ...] = field(default_factory=tuple)
    station_windows: dict[str, tuple[AccessWindow, ...]] = field(default_factory=dict)
    station_totals: dict[str, float] = field(default_factory=dict)
    station_aer: dict[str, tuple[AERRecord, ...]] = field(default_factory=dict)

    @property
    def total_duration_sec(self) -> float:
        return sum(w.duration_sec for w in self.windows)


def default_link_visibility_config() -> LinkVisibilityConfig:
    paths = PathsConfig.for_simulation("link_visibility")
    start_time, stop_time = current_local_day_period()
    return LinkVisibilityConfig(
        paths=paths,
        stk=STKConfig(mode="new", engine="python"),
        scenario=ScenarioConfig(
            name="LinkVisibility",
            start_time=start_time,
            stop_time=stop_time,
        ),
        satellite=SatelliteConfig(
            name="智慧天网-1 01A",
            ssc=59705,
            step=30.0,
            tle_url="https://celestrak.org/NORAD/elements/gp.php?CATNR=59705&FORMAT=TLE",
        ),
        stations=[
            LinkStationConfig(
                name="上海临港站",
                latitude_deg=30.903611,
                longitude_deg=121.919444,
                altitude_m=0.0,
                min_elevation_deg=15.0,
                gso_avoid_deg=15.0,
            ),
            LinkStationConfig(
                name="深圳飞思",
                latitude_deg=22.545,
                longitude_deg=114.078,
                altitude_m=0.0,
                min_elevation_deg=15.0,
                gso_avoid_deg=15.0,
            ),
        ],
    )
