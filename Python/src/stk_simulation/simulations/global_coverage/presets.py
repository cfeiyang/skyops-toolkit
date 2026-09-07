"""仿真场景文档规定的卫星和地面站模板。"""

from __future__ import annotations

from dataclasses import dataclass

from stk_simulation.infrastructure.tle import TLEData


@dataclass
class StationConfig:
    name: str
    lat: float
    lon: float
    alt: float
    min_elevation: float


@dataclass
class SatelliteElements:
    name: str
    ssc: int
    step: float
    epoch: float
    mean_motion: float
    eccentricity: float
    inclination: float
    arg_perigee: float
    raan: float
    mean_anomaly: float


def station_template(mode: str) -> list[StationConfig]:
    stations = [
        StationConfig(
            name="LinGang",
            lat=30.90361111,
            lon=121.91944444,
            alt=0,
            min_elevation=15,
        ),
        StationConfig(
            name="KaShi",
            lat=39.7730,
            lon=76.5128,
            alt=0,
            min_elevation=15,
        ),
        StationConfig(
            name="JiaMuSi",
            lat=47.99556,
            lon=134.05789,
            alt=0,
            min_elevation=15,
        ),
        StationConfig(
            name="HaiNan",
            lat=19.94,
            lon=109.57,
            alt=0,
            min_elevation=15,
        ),
        StationConfig(
            name="Mexico",
            lat=23.39,
            lon=-102.05,
            alt=0,
            min_elevation=15,
        ),
    ]

    counts = {"single": 1, "domestic": 4, "all": 5}
    try:
        count = counts[str(mode)]
    except KeyError as error:
        raise ValueError(
            "station_template: mode 必须是 single、domestic 或 all。"
        ) from error
    return stations[:count]


def derived_satellite_elements(tle: TLEData, step: float) -> list[SatelliteElements]:
    """用本次在线更新的根数生成第二、第三颗卫星。"""
    definitions = (
        ("TN02A", 90002, 45.0, -90.0),
        ("TN03A", 90003, 90.0, -180.0),
    )
    return [
        SatelliteElements(
            name=name,
            ssc=ssc,
            step=step,
            epoch=tle.epoch,
            mean_motion=tle.mean_motion,
            eccentricity=tle.eccentricity,
            inclination=tle.inclination,
            arg_perigee=tle.arg_perigee,
            raan=(tle.raan + raan_offset) % 360.0,
            mean_anomaly=(tle.mean_anomaly + anomaly_offset) % 360.0,
        )
        for name, ssc, raan_offset, anomaly_offset in definitions
    ]
