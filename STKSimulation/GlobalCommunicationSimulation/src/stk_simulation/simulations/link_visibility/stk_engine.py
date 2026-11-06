"""基于 STK 12.6 COM 接口的星地建链与 AER 计算引擎。

所有 agi.stk12 依赖都延迟到函数内部导入，保证未安装 STK 的电脑
导入本模块也不会崩溃。
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from stk_simulation.infrastructure.tle import load_latest_tle
from stk_simulation.simulations.common import OutputResult, _stk_time
from stk_simulation.simulations.link_visibility.config import (
    AERRecord,
    AccessWindow,
    LinkVisibilityConfig,
    LinkVisibilityResult,
)
from stk_simulation.simulations.link_visibility.py_engine import compute_link_visibility_python
from stk_simulation.stk.access import STKAccess
from stk_simulation.stk.session import STKSession

LOCAL_TZ = ZoneInfo("Asia/Shanghai")
TIME_FMT = "%Y-%m-%d %H:%M:%S"


def _fmt_bj(dt_utc: datetime) -> str:
    return dt_utc.astimezone(LOCAL_TZ).strftime(TIME_FMT)


def compute_link_visibility_stk(root, config: LinkVisibilityConfig) -> LinkVisibilityResult:
    """通过 STK 12 计算星地 Access 窗口与 AER 数据。"""
    # 延迟导入：objects.py / constraints.py 顶层依赖 agi.stk12
    from stk_simulation.stk.constraints import STKConstraints
    from stk_simulation.stk.objects import STKObjects

    tle = load_latest_tle(
        config.satellite.tle_url,
        config.paths.data_dir,
        config.satellite.ssc,
    )
    scenario = STKSession.create_scenario(
        root,
        config.scenario.name,
        config.scenario.start_time,
        config.scenario.stop_time,
    )
    sat = STKObjects.create_satellite_from_tle(
        root,
        scenario,
        "SAT_LINK",
        config.satellite.ssc,
        config.satellite.step,
        tle.path,
    )

    active_stations = config.stations[:2] if config.dual_station_sync else config.stations[:1]
    facilities = []
    for idx, st in enumerate(active_stations):
        fac = STKObjects.create_facility(
            scenario, f"Station_{idx + 1}", st.latitude_deg, st.longitude_deg, st.altitude_m / 1000.0
        )
        STKConstraints.set_min_elevation(fac, st.min_elevation_deg)
        facilities.append((st, fac))

    # 获取单站或双站交集窗口
    raw_intervals = STKAccess.compute_access_intervals(facilities[0][1], sat)
    if len(facilities) > 1:
        second_intervals = STKAccess.compute_access_intervals(facilities[1][1], sat)
        intersected: list[tuple[datetime, datetime]] = []
        for s1, e1 in raw_intervals:
            for s2, e2 in second_intervals:
                s_max = max(s1, s2)
                e_min = min(e1, e2)
                if e_min > s_max:
                    intersected.append((s_max, e_min))
        raw_intervals = intersected

    windows: list[AccessWindow] = []
    aer_records: list[AERRecord] = []

    for acc_num, (w_start, w_stop) in enumerate(raw_intervals, start=1):
        start_utcg = _stk_time(w_start.replace(tzinfo=None))
        stop_utcg = _stk_time(w_stop.replace(tzinfo=None))
        peak_el = -90.0
        peak_time = _fmt_bj(w_start)

        for st_cfg, fac_obj in facilities:
            rows = STKAccess.compute_aer_series(
                fac_obj, sat, start_utcg, stop_utcg, config.sample_step_sec
            )
            for row in rows:
                el_val = row["elevation_deg"]
                t_bj = _fmt_bj(row["dt_utc"])
                if el_val > peak_el:
                    peak_el = el_val
                    peak_time = t_bj
                aer_records.append(
                    AERRecord(
                        access_number=acc_num,
                        station_name=st_cfg.name,
                        time=t_bj,
                        azimuth_deg=row["azimuth_deg"],
                        elevation_deg=el_val,
                        range_km=row["range_km"],
                    )
                )

        windows.append(
            AccessWindow(
                access_number=acc_num,
                start_time=_fmt_bj(w_start),
                stop_time=_fmt_bj(w_stop),
                duration_sec=(w_stop - w_start).total_seconds(),
                max_elevation_deg=max(peak_el, 0.0),
                max_elevation_time=peak_time,
            )
        )

    # 复用轻量星下点轨迹用于绘图展示
    py_ref = compute_link_visibility_python(config)
    image_name = "link_visibility_stk.png"
    return LinkVisibilityResult(
        engine_used="stk",
        satellite_name=config.satellite.name,
        station_names=tuple(st.name for st in active_stations),
        start_time=py_ref.start_time,
        stop_time=py_ref.stop_time,
        windows=tuple(windows),
        aer_records=tuple(aer_records),
        ground_track=py_ref.ground_track,
        output=OutputResult(config.paths.result_dir, image_name, config.paths.result_dir / image_name),
        cfg=config,
    )
