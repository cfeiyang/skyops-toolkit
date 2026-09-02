from __future__ import annotations

from pathlib import Path

import numpy as np

_EARTH_R = 6378137.0
_K0 = np.cos(np.deg2rad(30.0))  # Behrmann 标准纬圈 ±30°


def dms2dd(deg: float, minutes: float, seconds: float) -> float:
    return deg + minutes / 60.0 + seconds / 3600.0


def wrap_lon(lon, lon_min: float):
    lon = np.asarray(lon, dtype=float)
    return np.mod(lon - lon_min, 360.0) + lon_min


def behrmann_fwd(lat, lon, center_lon: float = 120.0, radius: float = _EARTH_R):
    """Behrmann 等面积圆柱投影，对应 MATLAB defaultm('behrmann')。"""
    lat = np.asarray(lat, dtype=float)
    lon = np.asarray(lon, dtype=float)
    dlon = np.deg2rad(((lon - center_lon + 180.0) % 360.0) - 180.0)
    x = radius * dlon * _K0
    y = radius * np.sin(np.deg2rad(lat)) / _K0
    return x, y


def load_coastline(data_dir: str | Path | None = None):
    if data_dir is None:
        data_dir = Path(__file__).resolve().parents[1] / "data"
    path = Path(data_dir) / "coastline_110m.npz"
    packed = np.load(path)
    return packed["lat"], packed["lon"]
