"""使用 STK Desktop 计算两地 Access 和 AER。"""

from __future__ import annotations

from bisect import bisect_right
from datetime import datetime
from uuid import uuid4

from skyops_sim.simulations.common import OutputResult, _stk_time, parse_stk_time
from skyops_sim.simulations.link_visibility.config import (
    AERRecord, AccessWindow, LinkVisibilityConfig, LinkVisibilityResult,
)
from skyops_sim.simulations.link_visibility.py_engine import (
    _fmt_bj, _StationHandle, build_track, orbit_samples,
)
from skyops_sim.stk.desktop_bridge import STKDesktopBridge
from skyops_sim.stk.link_commands import build_scene

Interval = tuple[datetime, datetime]


def _collect_windows(desktop, scenario, stations, intervals, indices, sample_step):
    """为每个窗口按相同时间网格请求两站的 AER，保证导出时能逐行对齐。"""
    requests = [
        {"station": i, "start": _stk_time(start), "stop": _stk_time(stop)}
        for start, stop in intervals for i in indices
    ]
    if not requests:
        return (), ()
    response = desktop.request("sample", scenario=scenario, windows=requests, step=sample_step)
    series = iter(response["samples"])
    windows, records = [], []
    for number, (start, stop) in enumerate(intervals, 1):
        rows = []
        for index in indices:
            data = next(series)
            rows.extend(
                AERRecord(
                    number, stations[index].name, _fmt_bj(parse_stk_time(time)),
                    float(azimuth), float(elevation), float(distance),
                )
                for time, azimuth, elevation, distance in zip(
                    data["time"], data["azimuth"], data["elevation"], data["range"], strict=True
                )
            )
        peak = max(rows, key=lambda row: row.elevation_deg, default=None)
        windows.append(AccessWindow(
            number, _fmt_bj(start), _fmt_bj(stop), (stop - start).total_seconds(),
            peak.elevation_deg if peak else 0.0, peak.time if peak else _fmt_bj(start),
        ))
        records.extend(rows)
    return tuple(windows), tuple(records)


def _intersect(left: list[Interval], right: list[Interval]) -> list[Interval]:
    intersections = []
    i = j = 0
    while i < len(left) and j < len(right):
        start = max(left[i][0], right[j][0])
        end = min(left[i][1], right[j][1])
        if start < end:
            intersections.append((start, end))
        if left[i][1] <= right[j][1]:
            i += 1
        else:
            j += 1
    return intersections


def _visible_at(grid, intervals: list[Interval]) -> list[bool]:
    starts = [start for start, _ in intervals]
    indices = (bisect_right(starts, time) - 1 for time in grid)
    return [index >= 0 and time <= intervals[index][1] for time, index in zip(grid, indices)]


def compute_link_visibility_stk(
    desktop: STKDesktopBridge, config: LinkVisibilityConfig,
) -> LinkVisibilityResult:
    stations = config.stations[:2] if config.dual_station_sync else config.stations[:1]
    if not stations:
        raise ValueError("至少需要一个地面站。")
    current = desktop.connect(config.stk.mode)
    if current:
        raise RuntimeError(f"STK 已打开场景「{current}」。请先在 STK 中保存并关闭该场景，再计算建链。")
    tle = config.satellite.load_tle(config.paths.data_dir, local_file=config.tle_file)
    sat, ts, grid = orbit_samples(config, tle)
    scenario = f"LinkVisibility_{uuid4().hex[:10]}"
    commands, satellite, facilities = build_scene(scenario, config, tle, stations)
    result = desktop.request(
        "prepare", scenario=scenario, commands=commands,
        satellite=satellite, facilities=facilities,
    )
    intervals = [
        sorted((parse_stk_time(start), parse_stk_time(stop))
               for start, stop in zip(station["starts"], station["stops"], strict=True))
        for station in result["intervals"]
    ]
    if len(intervals) != len(stations):
        raise RuntimeError("STK 返回的站点数与配置不符。")
    combined = _intersect(*intervals) if len(stations) == 2 else intervals[0]
    step = max(config.sample_step_sec, 1.0)
    windows, aer = _collect_windows(
        desktop, scenario, stations, combined, tuple(range(len(stations))), step
    )
    station_windows, station_aer = {}, {}
    for index, (station, times) in enumerate(zip(stations, intervals)):
        station_windows[station.name], station_aer[station.name] = _collect_windows(
            desktop, scenario, stations, times, (index,), step
        )
    station_totals = {
        name: sum(window.duration_sec for window in rows) for name, rows in station_windows.items()
    }
    handles = [_StationHandle(ts, sat, station) for station in stations]
    visibility = [_visible_at(grid, times) for times in intervals]
    orbit, track = build_track(sat, ts, grid, handles, visibility)
    desktop.satellite_name = config.satellite.name
    image_name = "link_visibility_stk.png"
    return LinkVisibilityResult(
        engine_used="stk",
        satellite_name=config.satellite.name,
        station_names=tuple(station.name for station in stations),
        start_time=_fmt_bj(grid[0]),
        stop_time=_fmt_bj(grid[-1]),
        windows=windows,
        aer_records=aer,
        ground_track=track,
        orbit_track=orbit,
        tle_epoch=_fmt_bj(sat.epoch.utc_datetime()),
        station_windows=station_windows,
        station_totals=station_totals,
        station_aer=station_aer,
        output=OutputResult(config.paths.result_dir, image_name, config.paths.result_dir / image_name),
        cfg=config,
        stk_scenario=scenario,
    )
