"""星地建链预报统一调度服务（支持 STK / Python / 双引擎交叉精度对比）。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable

from stk_simulation.simulations.link_visibility.config import (
    EngineDiffItem,
    LinkVisibilityConfig,
    LinkVisibilityResult,
)
from stk_simulation.simulations.link_visibility.py_engine import (
    TIME_FMT,
    compute_link_visibility_python,
)


def run_link_visibility(
    root,
    config: LinkVisibilityConfig,
    run_mode: str = "normal",
    progress: Callable[[str], None] | None = None,
) -> LinkVisibilityResult:
    """运行星地建链仿真；run_mode='compare' 时同时跑双引擎并生成秒级精度对比表。"""
    if run_mode == "compare":
        if progress:
            progress("正在运行纯 Python (SGP4) 引擎计算建链窗口...")
        py_res = compute_link_visibility_python(config)
        if progress:
            progress("正在运行 STK 12.6 官方引擎计算 Access 窗口...")
        # 延迟导入：stk_engine 依赖 agi.stk12
        from stk_simulation.simulations.link_visibility.stk_engine import (
            compute_link_visibility_stk,
        )

        stk_res = compute_link_visibility_stk(root, config)

        # 按开始时间就近配对（带容差），避免窗口数不一致时按索引错位配对
        tolerance = timedelta(seconds=120)
        py_windows = list(py_res.windows)
        used_py: set[int] = set()
        diffs: list[EngineDiffItem] = []
        for sw in stk_res.windows:
            s_start = datetime.strptime(sw.start_time, TIME_FMT)
            best_idx: int | None = None
            best_delta: float | None = None
            for idx, pw in enumerate(py_windows):
                if idx in used_py:
                    continue
                p_start = datetime.strptime(pw.start_time, TIME_FMT)
                delta = abs((p_start - s_start).total_seconds())
                if delta <= tolerance.total_seconds() and (best_delta is None or delta < best_delta):
                    best_idx, best_delta = idx, delta
            if best_idx is None:
                continue  # 该 STK 窗口在 Python 引擎中无对应窗口，跳过
            used_py.add(best_idx)
            pw = py_windows[best_idx]
            s_stop = datetime.strptime(sw.stop_time, TIME_FMT)
            p_stop = datetime.strptime(pw.stop_time, TIME_FMT)
            diffs.append(
                EngineDiffItem(
                    access_number=sw.access_number,
                    stk_start=sw.start_time,
                    py_start=pw.start_time,
                    start_diff_sec=(p_start - s_start).total_seconds(),
                    stk_stop=sw.stop_time,
                    py_stop=pw.stop_time,
                    stop_diff_sec=(p_stop - s_stop).total_seconds(),
                    max_el_diff_deg=pw.max_elevation_deg - sw.max_elevation_deg,
                )
            )
        py_res.engine_used = "compare"
        py_res.diff_items = tuple(diffs)
        return py_res

    if getattr(config.stk, "engine", "python") == "stk" and root is not None:
        if progress:
            progress("[STK 引擎] 正在计算星地建链 Access 与 AER...")
        from stk_simulation.simulations.link_visibility.stk_engine import (
            compute_link_visibility_stk,
        )

        return compute_link_visibility_stk(root, config)

    if progress:
        progress("[Python 引擎] 正在计算 SGP4 星地建链与二分法精化窗口...")
    return compute_link_visibility_python(config)
