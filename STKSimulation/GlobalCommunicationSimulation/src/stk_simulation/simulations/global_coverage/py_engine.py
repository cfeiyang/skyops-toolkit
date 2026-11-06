"""纯 Python 向量化全球通信覆盖计算引擎（免 STK 商业授权，支持多星几何中继）。"""

from __future__ import annotations

from datetime import datetime, timedelta
from math import asin, atan2, cos, degrees, pi, radians, sin, sqrt
from typing import Callable

import numpy as np
import pandas as pd
from sgp4.api import Satrec, WGS72, jday

from stk_simulation.infrastructure.tle import TLEData, load_latest_tle
from stk_simulation.simulations.common import OutputResult, parse_stk_time
from stk_simulation.simulations.global_coverage.config import GlobalCoverageConfig
from stk_simulation.simulations.global_coverage.presets import derived_satellite_elements
from stk_simulation.simulations.global_coverage.service import (
    GlobalCoverageResult,
    GlobalCoverageSummary,
)

EARTH_RADIUS_KM = 6378.137
EARTH_FLAT = 1.0 / 298.257223563
ISL_MIN_TANGENT_ALT_KM = 80.0  # 星间链路最低切线高度（避开稠密大气与地表遮挡）


def _gmst_rad(jd_ut1: float) -> np.ndarray | float:
    """IAU 1982 格林尼治恒星时 (弧度)。"""
    t = (jd_ut1 - 2451545.0) / 36525.0
    sec = (
        67310.54841
        + (876600.0 * 3600.0 + 8640184.812866) * t
        + 0.093104 * (t ** 2)
        - 6.2e-6 * (t ** 3)
    )
    return np.deg2rad((sec / 240.0) % 360.0)


def _teme_to_ecef(r_teme: np.ndarray, jd_array: np.ndarray) -> np.ndarray:
    """将 (T, 3) 的 TEME 坐标旋转为 ECEF 地固坐标 (km)。"""
    theta = _gmst_rad(jd_array)
    c = np.cos(theta)
    s = np.sin(theta)
    x = c * r_teme[:, 0] + s * r_teme[:, 1]
    y = -s * r_teme[:, 0] + c * r_teme[:, 1]
    z = r_teme[:, 2]
    return np.stack([x, y, z], axis=-1)


def _geodetic_to_ecef_enu(
    lat_deg: np.ndarray, lon_deg: np.ndarray, alt_m: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """将地理经纬高转换为 ECEF 坐标 (N, 3) 与向上法向量 Up (N, 3)。"""
    lat = np.deg2rad(lat_deg)
    lon = np.deg2rad(lon_deg)
    alt_km = alt_m / 1000.0
    e2 = EARTH_FLAT * (2.0 - EARTH_FLAT)
    sin_lat = np.sin(lat)
    cos_lat = np.cos(lat)
    cos_lon = np.cos(lon)
    sin_lon = np.sin(lon)

    n_rad = EARTH_RADIUS_KM / np.sqrt(1.0 - e2 * sin_lat * sin_lat)
    x = (n_rad + alt_km) * cos_lat * cos_lon
    y = (n_rad + alt_km) * cos_lat * sin_lon
    z = (n_rad * (1.0 - e2) + alt_km) * sin_lat
    pos = np.stack([x, y, z], axis=-1)

    up = np.stack([cos_lat * cos_lon, cos_lat * sin_lon, sin_lat], axis=-1)
    return pos, up


def _ecef_to_latlon(r_ecef: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """ECEF (T, 3) 转星下点纬度、经度 (度)。"""
    x, y, z = r_ecef[:, 0], r_ecef[:, 1], r_ecef[:, 2]
    lon = np.rad2deg(np.arctan2(y, x))
    r_xy = np.hypot(x, y)
    lat = np.rad2deg(np.arctan2(z, r_xy * (1.0 - EARTH_FLAT) ** 2))
    return lat, lon


def _build_satrec_from_tle_file(tle_path) -> Satrec:
    lines = [
        line.strip()
        for line in tle_path.read_text(encoding="ascii").splitlines()
        if line.strip()
    ]
    l1 = next(line for line in lines if line.startswith("1 "))
    l2 = next(line for line in lines if line.startswith("2 "))
    return Satrec.twoline2rv(l1, l2, WGS72)


def _build_satrec_from_elements(elem, ref_sat: Satrec) -> Satrec:
    """利用参考星的阻尼项与轨道根数构造派生卫星的 SGP4 算子。

    注意单位：presets.py 的 mean_motion 为 度/秒，sgp4init 的 no_kozai
    要求 弧度/分，故 radians(mean_motion) * 60 正是换算。
    """
    sat = Satrec()
    sat.sgp4init(
        WGS72,
        "i",
        elem.ssc,
        ref_sat.jdsatepoch - 2433281.5,  # sgp4 2.x 的 jdsatepoch 已含小数日，勿再加 jdsatepochF
        ref_sat.bstar,
        ref_sat.ndot,
        ref_sat.nddot,
        elem.eccentricity,
        radians(elem.arg_perigee),
        radians(elem.inclination),
        radians(elem.mean_anomaly),
        radians(elem.mean_motion) * 60.0,  # 度/秒 -> 弧度/分
        radians(elem.raan),
    )
    return sat


def _isl_visible_matrix(sat_ecef: np.ndarray) -> np.ndarray:
    """计算 (T, S, S) 布尔矩阵：判断任意两颗卫星之间是否存在无地球遮挡的几何视线。"""
    t_steps, s_count, _ = sat_ecef.shape
    isl = np.zeros((t_steps, s_count, s_count), dtype=bool)
    min_r2 = (EARTH_RADIUS_KM + ISL_MIN_TANGENT_ALT_KM) ** 2

    for i in range(s_count):
        for j in range(i + 1, s_count):
            r1 = sat_ecef[:, i, :]  # (T, 3)
            r2 = sat_ecef[:, j, :]  # (T, 3)
            d = r2 - r1
            d_norm2 = np.einsum("ij,ij->i", d, d)
            # 线段 R1 + u*(R2 - R1) 离地心最近点的参数 u
            u = -np.einsum("ij,ij->i", r1, d) / np.maximum(d_norm2, 1e-9)
            u_clamped = np.clip(u, 0.0, 1.0)[:, None]
            closest = r1 + u_clamped * d
            closest_r2 = np.einsum("ij,ij->i", closest, closest)
            ok = closest_r2 >= min_r2
            isl[:, i, j] = ok
            isl[:, j, i] = ok
    return isl


def compute_global_coverage_python(
    config: GlobalCoverageConfig,
    *,
    tle: TLEData | None = None,
    progress: Callable[[str], None] | None = None,
) -> GlobalCoverageResult:
    """纯 Python 向量化计算全球通信覆盖时长，输出与 STK 完全同构的 GlobalCoverageResult。"""
    if progress:
        progress("[Python 引擎] 正在加载 TLE 轨道根数...")
    tle = tle or load_latest_tle(
        config.satellite.tle_url,
        config.paths.data_dir,
        config.satellite.ssc,
    )

    start_dt = parse_stk_time(config.scenario.start_time)
    stop_dt = parse_stk_time(config.scenario.stop_time)
    step_sec = float(max(config.satellite.step, 10.0))
    total_sec = max((stop_dt - start_dt).total_seconds(), step_sec)
    num_steps = int(total_sec // step_sec) + 1

    times = [start_dt + timedelta(seconds=i * step_sec) for i in range(num_steps)]
    jd_list, fr_list = zip(
        *(
            jday(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second + dt.microsecond / 1e6)
            for dt in times
        )
    )
    jd_arr = np.asarray(jd_list, dtype=float)
    fr_arr = np.asarray(fr_list, dtype=float)
    jd_full = jd_arr + fr_arr

    # 1. 构建卫星列表并传播轨迹
    ref_sat = _build_satrec_from_tle_file(tle.path)
    sat_models = [(config.satellite.name, ref_sat)]
    if config.satellite_group.mode != "single":
        for elem in derived_satellite_elements(tle, step_sec):
            sat_models.append((elem.name, _build_satrec_from_elements(elem, ref_sat)))

    s_count = len(sat_models)
    sat_ecef = np.zeros((num_steps, s_count, 3), dtype=float)
    tracks: list[tuple[np.ndarray, np.ndarray]] = []

    if progress:
        progress(f"[Python 引擎] 正在外推 {s_count} 颗卫星的 SGP4 轨道位置...")

    for s_idx, (_, sat_obj) in enumerate(sat_models):
        err, r_teme, _ = sat_obj.sgp4_array(jd_arr, fr_arr)
        if np.any(err != 0):
            raise RuntimeError(f"SGP4 轨道外推异常，错误码: {np.unique(err)}")
        ecef = _teme_to_ecef(r_teme, jd_full)
        sat_ecef[:, s_idx, :] = ecef

        lat, lon = _ecef_to_latlon(ecef)
        lon_wrapped = np.mod(lon - config.plot.lon_range[0], 360.0) + config.plot.lon_range[0]
        jumps = np.concatenate(([False], np.abs(np.diff(lon_wrapped)) > 180.0))
        tracks.append((np.where(jumps, np.nan, lat), np.where(jumps, np.nan, lon_wrapped)))

    # 2. 计算地面站对各卫星的可见性 (T, S)
    # 注意：presets.StationConfig 的 alt 单位是 km，这里换算为米。
    st_lats = np.array([st.lat for st in config.stations], dtype=float)
    st_lons = np.array([st.lon for st in config.stations], dtype=float)
    st_alts = np.array([st.alt * 1000.0 for st in config.stations], dtype=float)
    st_min_sin = np.sin(np.deg2rad([st.min_elevation for st in config.stations]))
    st_pos, st_up = _geodetic_to_ecef_enu(st_lats, st_lons, st_alts)  # (K, 3)

    # 相对矢量: (T, S, K, 3)
    diff_st = sat_ecef[:, :, None, :] - st_pos[None, None, :, :]
    dist_st = np.linalg.norm(diff_st, axis=-1)
    sin_el_st = np.einsum("tski,ki->tsk", diff_st, st_up) / np.maximum(dist_st, 1e-9)
    st_sat_vis = sin_el_st >= st_min_sin[None, None, :]  # (T, S, K)
    any_station_vis = np.any(st_sat_vis, axis=-1)  # (T, S) 任意地面站可见该卫星

    # 3. 若开启多星几何星间中继，计算每颗卫星是否能连通地面站 (直达或经过 1 跳星间链路)
    if config.satellite_group.mode == "single" or s_count == 1:
        sat_connected_to_ground = any_station_vis[:, :1]  # (T, 1)
    else:
        isl_ok = _isl_visible_matrix(sat_ecef)  # (T, S, S)
        relay_vis = np.any(isl_ok & any_station_vis[:, None, :], axis=-1)  # (T, S)
        sat_connected_to_ground = any_station_vis | relay_vis  # (T, S)

    # 4. 生成全球覆盖网格并分块向量化计算覆盖时长
    res = float(max(config.coverage.resolution, 0.25))
    lats = np.arange(-90.0, 90.0 + 1e-6, res)
    lons = np.arange(-180.0, 180.0, res)
    lon_grid, lat_grid = np.meshgrid(lons, lats)
    flat_lats = lat_grid.ravel()
    flat_lons = lon_grid.ravel()
    total_points = flat_lats.size

    grid_pos, grid_up = _geodetic_to_ecef_enu(
        flat_lats, flat_lons, np.zeros_like(flat_lats)
    )
    min_sin_grid = sin(radians(config.coverage.min_elevation))
    min_assets = max(int(config.fom.min_assets), 1)

    covered_steps = np.zeros(total_points, dtype=np.int32)
    chunk_size = 1800  # 分块广播，兼顾极速计算与低内存占用
    active_sats = 1 if config.satellite_group.mode == "single" else s_count

    for start_idx in range(0, total_points, chunk_size):
        end_idx = min(start_idx + chunk_size, total_points)
        if progress:
            pct = int(end_idx * 100 / total_points)
            progress(f"[Python 引擎] 正在解算全球网格覆盖 ({pct}%)...")

        g_pos = grid_pos[start_idx:end_idx]  # (C, 3)
        g_up = grid_up[start_idx:end_idx]    # (C, 3)

        # (T, S, C, 3)
        d_vec = sat_ecef[:, :active_sats, None, :] - g_pos[None, None, :, :]
        d_norm = np.linalg.norm(d_vec, axis=-1)
        sin_el = np.einsum("tsci,ci->tsc", d_vec, g_up) / np.maximum(d_norm, 1e-9)
        grid_sees_sat = sin_el >= min_sin_grid  # (T, S, C)

        # 端到端链路导通 = 网格点看见卫星 & 该卫星此刻连通地面站
        end_to_end = grid_sees_sat & sat_connected_to_ground[:, :active_sats, None]
        active_count = np.sum(end_to_end, axis=1)  # (T, C)
        point_active = active_count >= min_assets   # (T, C)
        covered_steps[start_idx:end_idx] = np.sum(point_active, axis=0)

    # 修正首尾时间步权重
    time_sec = covered_steps.astype(float) * (total_sec / max(num_steps - 1, 1))
    time_sec = np.minimum(time_sec, total_sec)
    time_hour = time_sec / 3600.0

    coverage_df = pd.DataFrame(
        {
            "LatitudeDeg": flat_lats,
            "LongitudeDeg": np.mod(flat_lons, 360.0),
            "TimeSec": time_sec,
            "TimeHour": time_hour,
        }
    )

    sat_names = [name for name, _ in sat_models[:active_sats]]
    st_names = [st.name for st in config.stations]
    image_name = config.output.image_name or (
        f"py_global_coverage_{len(sat_names)}sat_{len(st_names)}station.png"
    )
    config.output.image_name = image_name
    config.plot.title = (
        f"[Python 引擎] {'/'.join(sat_names)}-{'/'.join(st_names)} "
        f"全球通信时长（{len(sat_names)}星×{len(st_names)}站）"
    )
    image_path = config.paths.result_dir / image_name

    return GlobalCoverageResult(
        coverage_data=coverage_df,
        satellite_tracks=tracks[:active_sats],
        summary=GlobalCoverageSummary(
            satellite_count=len(sat_names),
            station_count=len(st_names),
            max_hour=float(coverage_df["TimeHour"].max(skipna=True)),
        ),
        output=OutputResult(config.paths.result_dir, image_name, image_path),
        cfg=config,
    )
