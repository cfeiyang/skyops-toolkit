"""界面与 STK 服务之间传递的数据。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StationConfig:
    name: str
    latitude_deg: float
    longitude_deg: float
    altitude_m: float
    min_elevation_deg: float


@dataclass(frozen=True)
class ScenarioRequest:
    stk_mode: str
    scenario_name: str
    start_time: str
    stop_time: str
    satellite_name: str
    satellite_ssc: int
    propagation_step_sec: float
    tle_url: str
    stations: tuple[StationConfig, ...]


@dataclass(frozen=True)
class ScenarioResult:
    scenario_name: str
    satellite_name: str
    tle_name: str
    station_count: int
    start_time: str
    stop_time: str

