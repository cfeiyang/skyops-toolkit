"""仿真场景文档规定的卫星和地面站模板。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from stk_simulation.utils.geo import dms2dd


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
            lat=dms2dd(30, 54, 13),
            lon=dms2dd(121, 55, 10),
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


def satellites_from_reference_tle(
    tle_file: str | Path,
    reference_ssc: int,
    reference_name: str,
    step: float,
) -> list[SatelliteElements]:
    """读取参考星 TLE，并按文档的 RAAN/M 偏置生成三星根数。"""
    reference = _read_tle_elements(tle_file, reference_ssc, reference_name, step)
    definitions = (
        (reference_name, reference_ssc, 0.0, 0.0),
        ("TN02A", 90002, 45.0, -90.0),
        ("TN03A", 90003, 90.0, -180.0),
    )
    return [
        SatelliteElements(
            name=name,
            ssc=ssc,
            step=reference.step,
            epoch=reference.epoch,
            mean_motion=reference.mean_motion,
            eccentricity=reference.eccentricity,
            inclination=reference.inclination,
            arg_perigee=reference.arg_perigee,
            raan=(reference.raan + raan_offset) % 360.0,
            mean_anomaly=(reference.mean_anomaly + anomaly_offset) % 360.0,
        )
        for name, ssc, raan_offset, anomaly_offset in definitions
    ]


def _read_tle_elements(
    tle_file: str | Path,
    ssc: int,
    name: str,
    step: float,
) -> SatelliteElements:
    path = Path(tle_file)
    if not path.is_file():
        raise FileNotFoundError(f"TLE 文件不存在：{path}")

    lines = [line.rstrip() for line in path.read_text(encoding="utf-8-sig").splitlines()]
    target = str(ssc)
    for index, line1 in enumerate(lines[:-1]):
        if not line1.startswith("1 ") or line1[2:7].strip() != target:
            continue
        line2 = lines[index + 1]
        if not line2.startswith("2 ") or line2[2:7].strip() != target:
            continue
        try:
            return SatelliteElements(
                name=name,
                ssc=ssc,
                step=step,
                epoch=float(line1[18:32]),
                inclination=float(line2[8:16]),
                raan=float(line2[17:25]),
                eccentricity=float(f"0.{line2[26:33].strip()}"),
                arg_perigee=float(line2[34:42]),
                mean_anomaly=float(line2[43:51]),
                mean_motion=float(line2[52:63]) * 360.0 / 86400.0,
            )
        except (ValueError, IndexError) as error:
            raise ValueError(f"TLE 中 SSC={ssc} 的轨道根数格式无效：{path}") from error
    raise ValueError(f"TLE 中没有找到 SSC={ssc} 的两行根数：{path}")
