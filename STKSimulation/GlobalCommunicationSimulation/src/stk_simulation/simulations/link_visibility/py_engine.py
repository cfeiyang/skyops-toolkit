"""基于 Skyfield SGP4 + 二分法的星地建链可见性纯 Python 计算引擎。

输出富结果：
- combined windows（两地同时通信）与 aer_samples；
- 每个地面站各自的可用窗口与累计时长（station_windows / station_totals）；
- 星下点轨迹 TrackPoint（含 el1/linked1/el2/linked2/comm），供世界地图动画。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Sequence
from zoneinfo import ZoneInfo

import numpy as np
from skyfield.api import EarthSatellite, Loader, wgs84

from stk_simulation.infrastructure.tle import load_latest_tle
from stk_simulation.simulations.common import OutputResult, parse_stk_time
from stk_simulation.simulations.link_visibility.config import (
    AERRecord,
    AccessWindow,
    LinkStationConfig,
    LinkVisibilityConfig,
    LinkVisibilityResult,
    TrackPoint,
)

LOCAL_TZ = ZoneInfo("Asia/Shanghai")
TIME_FMT = "%Y-%m-%d %H:%M:%S"
GEO_RADIUS_KM = 42164.0
EARTH_RADIUS_KM = 6371.0


def _fmt_bj(dt_utc: datetime) -> str:
    return dt_utc.astimezone(LOCAL_TZ).strftime(TIME_FMT)


def _gso_arc(station: LinkStationConfig, step_deg: float = 2.0) -> np.ndarray:
    lat = np.radians(station.latitude_deg)
    lon = np.radians(station.longitude_deg)
    sx = EARTH_RADIUS_KM * np.cos(lat) * np.cos(lon)
    sy = EARTH_RADIUS_KM * np.cos(lat) * np.sin(lon)
    sz = EARTH_RADIUS_KM * np.sin(lat)

    east = np.array([-np.sin(lon), np.cos(lon), 0.0])
    north = np.array([-np.sin(lat) * np.cos(lon), -np.sin(lat) * np.sin(lon), np.cos(lat)])
    up = np.array([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)])

    rows = []
    for g_lon in np.arange(-180.0, 180.0, step_deg):
        gl = np.radians(float(g_lon))
        d = np.array([GEO_RADIUS_KM * np.cos(gl) - sx, GEO_RADIUS_KM * np.sin(gl) - sy, -sz])
        dist = float(np.linalg.norm(d))
        if dist <= 0.0:
            continue
        el = float(np.degrees(np.arcsin(np.clip(float(d @ up) / dist, -1.0, 1.0))))
        if el <= 0.0:
            continue
        az = float(np.degrees(np.arctan2(float(d @ east), float(d @ north))) % 360.0)
        rows.append((az, el))
    return np.array(rows, dtype=float) if rows else np.zeros((0, 2), dtype=float)


def _gso_sep_deg(az_deg, el_deg, arc: np.ndarray) -> np.ndarray:
    az = np.radians(np.asarray(az_deg, dtype=float))
    el = np.radians(np.asarray(el_deg, dtype=float))
    if arc is None or len(arc) == 0:
        return np.full(np.shape(az), 90.0)
    arc_az = np.radians(arc[:, 0])
    arc_el = np.radians(arc[:, 1])
    cos_sep = (
        np.sin(el)[..., None] * np.sin(arc_el)[None, ...]
        + np.cos(el)[..., None] * np.cos(arc_el)[None, ...] * np.cos(az[..., None] - arc_az[None, ...])
    )
    return np.squeeze(np.degrees(np.arccos(np.clip(cos_sep, -1.0, 1.0))).min(axis=-1))


def _mask_elevation(az_deg, base_min: float, mask: Sequence[tuple[float, float, float]]):
    az = np.asarray(az_deg, dtype=float)
    eff = np.full(np.shape(az), float(base_min), dtype=float)
    for s, e, el in mask:
        s, e = float(s) % 360.0, float(e) % 360.0
        if abs(s - e) < 1e-9:
            continue
        inside = ((az >= s) & (az < e)) if s < e else ((az >= s) | (az < e))
        eff = np.maximum(eff, np.where(inside, float(el), -1e9))
    return eff


class _StationHandle:
    def __init__(self, ts, sat, st: LinkStationConfig) -> None:
        self.station = st
        self.ts = ts
        self.topocentric = sat - wgs84.latlon(st.latitude_deg, st.longitude_deg, elevation_m=st.altitude_m)
        self.gso_arc = _gso_arc(st) if st.gso_avoid_deg > 0 else np.zeros((0, 2))

    def altaz(self, t):
        return self.topocentric.at(t).altaz()

    def visible_at(self, t):
        alt, az, _ = self.altaz(t)
        min_el = _mask_elevation(az.degrees, self.station.min_elevation_deg, self.station.mask)
        ok = alt.degrees >= min_el
        if self.station.gso_avoid_deg > 0 and len(self.gso_arc):
            sep = _gso_sep_deg(az.degrees, alt.degrees, self.gso_arc)
            ok = ok & (sep >= self.station.gso_avoid_deg)
        return ok


def _extract_windows(handles, grid, ts, config: LinkVisibilityConfig):
    """按给定站点集合（交集）提取可见窗口与 AER 采样。"""
    combined = np.asarray(handles[0].visible_at(ts.from_datetimes(grid)), dtype=bool)
    for h in handles[1:]:
        combined = combined & np.asarray(h.visible_at(ts.from_datetimes(grid)), dtype=bool)

    windows: list[AccessWindow] = []
    aer_records: list[AERRecord] = []
    i, n = 0, len(combined)
    acc_num = 0
    while i < n:
        if not combined[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and combined[j + 1]:
            j += 1
        acc_num += 1

        w_start = grid[i]
        if i > 0:
            lo, hi = grid[i - 1], grid[i]
            while (hi - lo).total_seconds() > config.refine_step_sec:
                mid = lo + (hi - lo) / 2
                if all(bool(h.visible_at(ts.from_datetime(mid))) for h in handles):
                    hi = mid
                else:
                    lo = mid
            w_start = hi

        w_stop = grid[j]
        if j < n - 1:
            lo, hi = grid[j], grid[j + 1]
            while (hi - lo).total_seconds() > config.refine_step_sec:
                mid = lo + (hi - lo) / 2
                if all(bool(h.visible_at(ts.from_datetime(mid))) for h in handles):
                    lo = mid
                else:
                    hi = mid
            w_stop = lo

        dur = max((w_stop - w_start).total_seconds(), 0.0)
        s_step = float(max(config.sample_step_sec, 1.0))
        s_times = [w_start + timedelta(seconds=k * s_step) for k in range(int(dur // s_step) + 1)]
        if (w_stop - s_times[-1]).total_seconds() > 0.5:
            s_times.append(w_stop)
        t_win = ts.from_datetimes(s_times)

        peak_el = -90.0
        peak_time_str = _fmt_bj(w_start)
        for h in handles:
            alt, az, dist = h.altaz(t_win)
            for idx, dt in enumerate(s_times):
                el_val = float(alt.degrees[idx])
                if el_val > peak_el:
                    peak_el = el_val
                    peak_time_str = _fmt_bj(dt)
                aer_records.append(
                    AERRecord(
                        access_number=acc_num,
                        station_name=h.station.name,
                        time=_fmt_bj(dt),
                        azimuth_deg=float(az.degrees[idx]),
                        elevation_deg=el_val,
                        range_km=float(dist.km[idx]),
                    )
                )

        windows.append(
            AccessWindow(
                access_number=acc_num,
                start_time=_fmt_bj(w_start),
                stop_time=_fmt_bj(w_stop),
                duration_sec=dur,
                max_elevation_deg=peak_el,
                max_elevation_time=peak_time_str,
            )
        )
        i = j + 1
    return tuple(windows), aer_records


def _read_tle_lines(config: LinkVisibilityConfig) -> tuple[str, str, str]:
    """返回 (line1, line2, 来源说明)。本地文件优先，否则在线。"""
    if config.tle_file:
        path = Path(config.tle_file)
        if not path.is_file():
            raise ValueError(f"TLE 文件不存在：{path}")
        lines = [ln.strip() for ln in path.read_text(encoding="ascii", errors="replace").splitlines() if ln.strip()]
        line1 = next((ln for ln in lines if ln.startswith("1 ")), "")
        line2 = next((ln for ln in lines if ln.startswith("2 ")), "")
        if not line1 or not line2:
            raise ValueError("TLE 文件中未找到两行根数（应以 '1 ' 与 '2 ' 开头）。")
        return line1, line2, f"本地文件 {path.name}"

    tle = load_latest_tle(config.satellite.tle_url, config.paths.data_dir, config.satellite.ssc)
    lines = [ln.strip() for ln in tle.path.read_text(encoding="ascii").splitlines() if ln.strip()]
    line1 = next(ln for ln in lines if ln.startswith("1 "))
    line2 = next(ln for ln in lines if ln.startswith("2 "))
    return line1, line2, f"在线 {tle.path.name}"


def compute_link_visibility_python(config: LinkVisibilityConfig) -> LinkVisibilityResult:
    """运行纯 Python 星地建链与 AER 计算，输出含单站窗口与合并轨迹的富结果。"""
    line1, line2, tle_source = _read_tle_lines(config)

    stations = list(config.stations[:2])
    if not stations:
        raise ValueError("至少需要一个地面站。")

    loader = Loader(str(config.paths.data_dir))
    ts = loader.timescale(builtin=True)
    sat = EarthSatellite(line1, line2, config.satellite.name, ts)
    handles = [_StationHandle(ts, sat, st) for st in stations]

    start_utc = parse_stk_time(config.scenario.start_time)
    stop_utc = parse_stk_time(config.scenario.stop_time)
    if stop_utc <= start_utc:
        raise ValueError("结束时间必须晚于开始时间。")
    if (stop_utc - start_utc).total_seconds() > 8 * 86400.0:
        raise ValueError("仿真时段超过 8 天，请缩小时间范围。")
    span_sec = max((stop_utc - start_utc).total_seconds(), 60.0)
    step = float(max(config.coarse_step_sec, 5.0))
    grid = [start_utc + timedelta(seconds=i * step) for i in range(int(span_sec // step) + 1)]
    if (stop_utc - grid[-1]).total_seconds() > 1.0:
        grid.append(stop_utc)
    t_grid = ts.from_datetimes(grid)

    # 两地通信窗口 + AER
    combined_windows, aer_records = _extract_windows(handles, grid, ts, config)

    # 单站窗口与累计时长 + 单站 AER 采样
    station_windows: dict[str, tuple[AccessWindow, ...]] = {}
    station_totals: dict[str, float] = {}
    station_aer: dict[str, tuple[AERRecord, ...]] = {}
    for h in handles:
        ws, aer = _extract_windows([h], grid, ts, config)
        station_windows[h.station.name] = ws
        station_totals[h.station.name] = sum(w.duration_sec for w in ws)
        station_aer[h.station.name] = tuple(aer)

    # 星下点轨迹 + 单站建链状态
    sub = sat.at(t_grid).subpoint()
    vis = [np.asarray(h.visible_at(t_grid), dtype=bool) for h in handles]
    els = [np.asarray(h.altaz(t_grid)[0].degrees) for h in handles]
    track = []
    for idx, dt in enumerate(grid):
        linked1 = bool(vis[0][idx])
        linked2 = bool(vis[1][idx]) if len(handles) > 1 else False
        el1 = float(els[0][idx])
        el2 = float(els[1][idx]) if len(handles) > 1 else 0.0
        track.append(
            TrackPoint(
                time=_fmt_bj(dt),
                latitude_deg=float(sub.latitude.degrees[idx]),
                longitude_deg=float(sub.longitude.degrees[idx]),
                elevation_deg=el1,
                linked=bool(linked1 and linked2),
                el1=el1,
                linked1=linked1,
                el2=el2,
                linked2=linked2,
            )
        )

    image_name = "link_visibility_python.png"
    return LinkVisibilityResult(
        engine_used="python",
        satellite_name=config.satellite.name,
        station_names=tuple(st.name for st in stations),
        start_time=_fmt_bj(start_utc),
        stop_time=_fmt_bj(stop_utc),
        windows=combined_windows,
        aer_records=tuple(aer_records),
        ground_track=tuple(track),
        station_windows=station_windows,
        station_totals=station_totals,
        station_aer=station_aer,
        output=OutputResult(config.paths.result_dir, image_name, config.paths.result_dir / image_name),
        cfg=config,
    )
