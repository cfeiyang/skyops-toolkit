"""界面与 STK 服务之间传递的数据模型。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StationConfig:
    name: str
    latitude_deg: float
    longitude_deg: float
    altitude_m: float
    min_elevation_deg: float
    sun_exclusion_deg: float


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
    analysis_station_name: str
    aer_step_sec: float


@dataclass(frozen=True)
class AccessInterval:
    access_number: int
    start_time: str
    stop_time: str
    duration_sec: float


@dataclass(frozen=True)
class AERSample:
    access_number: int
    time: str
    azimuth_deg: float
    elevation_deg: float
    range_km: float


@dataclass(frozen=True)
class ScenarioResult:
    scenario_name: str
    satellite_name: str
    tle_name: str
    station_count: int
    start_time: str
    stop_time: str
    analysis_station_name: str
    analysis_min_elevation_deg: float
    analysis_sun_exclusion_deg: float
    access_intervals: tuple[AccessInterval, ...]
    aer_samples: tuple[AERSample, ...]
