from __future__ import annotations

from copy import deepcopy

from utils.geo import dms2dd


def station_template(mode: str) -> list[dict]:
    stations = [
        {
            "name": "LinGang",
            "lat": dms2dd(30, 54, 13),
            "lon": dms2dd(121, 55, 10),
            "alt": 0,
            "min_elevation": 15,
            "enabled": True,
        },
        {
            "name": "KaShi",
            "lat": 39.7730,
            "lon": 76.5128,
            "alt": 0,
            "min_elevation": 15,
            "enabled": True,
        },
        {
            "name": "JiaMuSi",
            "lat": 47.99556,
            "lon": 134.05789,
            "alt": 0,
            "min_elevation": 15,
            "enabled": True,
        },
        {
            "name": "WenChang",
            "lat": 19.6143,
            "lon": 110.9511,
            "alt": 0,
            "min_elevation": 15,
            "enabled": True,
        },
    ]
    count = {"single": 1, "two": 2, "three": 3, "four": 4}.get(str(mode))
    if count is None:
        raise ValueError("地面站模式必须是 single、two、three 或 four。")
    return deepcopy(stations[:count])


def satellite_template(mode: str) -> list[dict]:
    mean_motion = 2.00562166 * 360 / 86400
    sats = [
        {
            "name": "TN01A",
            "ssc": 59705,
            "step": 60,
            "epoch": 26242.91536755,
            "mean_motion": mean_motion,
            "eccentricity": 0.0028567,
            "inclination": 53.1278,
            "arg_perigee": 203.6024,
            "raan": 167.5041,
            "mean_anomaly": 156.2820,
        },
        {
            "name": "TN02A",
            "ssc": 90002,
            "step": 60,
            "epoch": 26242.91536755,
            "mean_motion": mean_motion,
            "eccentricity": 0.0028567,
            "inclination": 53.1278,
            "arg_perigee": 203.6024,
            "raan": 212.5041,
            "mean_anomaly": 66.2820,
        },
        {
            "name": "TN03A",
            "ssc": 90003,
            "step": 60,
            "epoch": 26242.91536755,
            "mean_motion": mean_motion,
            "eccentricity": 0.0028567,
            "inclination": 53.1278,
            "arg_perigee": 203.6024,
            "raan": 257.5041,
            "mean_anomaly": 336.2820,
        },
    ]
    if mode == "single":
        count = 1
    elif mode == "multi":
        count = 3
    else:
        raise ValueError("卫星模式必须是 single 或 multi。")
    return deepcopy(sats[:count])
