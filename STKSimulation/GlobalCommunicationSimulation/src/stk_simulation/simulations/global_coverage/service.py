"""全球通信时长仿真的计算、文档方案和输出流程。"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from stk_simulation.infrastructure.tle import TLEData, load_latest_tle
from stk_simulation.simulations.common import OutputResult
from stk_simulation.simulations.global_coverage.config import GlobalCoverageConfig
from stk_simulation.simulations.global_coverage.presets import (
    derived_satellite_elements,
    station_template,
)
from stk_simulation.stk.data import instance_name, numeric_dataset

# 说明：
# - STKChain / STKConstraints / STKCoverage / STKObjects / STKSession
#   改为函数内惰性导入 —— 这些模块顶层依赖 agi.stk12，
#   未安装 STK 的电脑走纯 Python 引擎时不应触发 ModuleNotFoundError；
# - matplotlib 与绘图函数（plot_global_coverage / save_axes_image）同样惰性导入，
#   使纯 Python 引擎只依赖 numpy/pandas/sgp4，无需安装 GUI 绘图栈即可跑通计算。


@dataclass
class GlobalCoverageSummary:
    satellite_count: int
    station_count: int
    max_hour: float


@dataclass
class CoverageGainSummary:
    station_name: str
    max_hour: float
    mean_positive_hour: float
    new_coverage_percent: float
    new_coverage_area_km2: float


@dataclass
class GlobalCoverageResult:
    coverage_data: pd.DataFrame
    satellite_tracks: list[tuple[np.ndarray, np.ndarray]]
    summary: GlobalCoverageSummary
    output: OutputResult
    cfg: GlobalCoverageConfig
    additional_images: tuple[Path, ...] = field(default_factory=tuple)
    comparison_results: tuple[tuple[str, "GlobalCoverageResult"], ...] = field(
        default_factory=tuple
    )
    gain_summary: CoverageGainSummary | None = None


def compute_global_coverage(
    root,
    config: GlobalCoverageConfig,
    *,
    tle: TLEData | None = None,
    progress: Callable[[str], None] | None = None,
) -> GlobalCoverageResult:
    """创建 STK 场景并提取绘图所需的全部数值，不操作 GUI。

    根据 config.stk.engine 自动选择 STK 官方引擎或纯 Python 向量化引擎；
    无 STK 环境（root 为 None）时自动回退到纯 Python 引擎。
    """
    if getattr(config.stk, "engine", "python") == "python" or root is None:
        from stk_simulation.simulations.global_coverage.py_engine import (
            compute_global_coverage_python,
        )

        return compute_global_coverage_python(config, tle=tle, progress=progress)

    # 惰性导入 STK 依赖模块（仅官方引擎路径需要）
    from stk_simulation.stk.chain import STKChain
    from stk_simulation.stk.constraints import STKConstraints
    from stk_simulation.stk.coverage import STKCoverage
    from stk_simulation.stk.objects import STKObjects
    from stk_simulation.stk.session import STKSession

    tle = tle or _load_reference_tle(config)
    scenario = STKSession.create_scenario(
        root,
        config.scenario.name,
        config.scenario.start_time,
        config.scenario.stop_time,
    )
    satellites = _create_satellites(root, scenario, config, tle)

    facilities = []
    for station in config.stations:
        facility = STKObjects.create_facility(
            scenario, station.name, station.lat, station.lon, station.alt
        )
        STKConstraints.set_min_elevation(facility, station.min_elevation)
        _apply_interference_avoidance(facility, config)
        facilities.append(facility)

    ground_node = STKObjects.create_ground_group(
        scenario, config.ground_group.name, facilities
    )
    if config.satellite_group.mode == "single":
        chains = [
            STKChain.create_sat_ground_chain(
                scenario, config.chain.name, ground_node, satellites[0]
            )
        ]
    else:
        chains = STKChain.create_satellite_network_chains(
            scenario, config.chain.name, ground_node, satellites
        )

    grid_seed = STKCoverage.create_coverage_grid_seed(
        scenario,
        config.coverage.grid_seed_name,
        config.coverage.min_elevation,
    )
    _apply_interference_avoidance(grid_seed, config)
    coverage = STKCoverage.create_global_coverage(
        scenario,
        config.coverage.name,
        config.coverage.resolution,
        chains,
        grid_seed,
    )
    fom = STKCoverage.create_coverage_time_fom(
        coverage, config.fom.name, config.fom.min_assets
    )
    coverage_data = STKCoverage.read_coverage_time(fom)
    tracks = [
        _read_satellite_track(satellite, scenario, config)
        for satellite in satellites
    ]

    satellite_names = [instance_name(satellite) for satellite in satellites]
    station_names = [station.name for station in config.stations]
    image_name = config.output.image_name or (
        f"global_coverage_{len(satellites)}sat_{len(config.stations)}station.png"
    )
    config.output.image_name = image_name
    config.plot.title = (
        f"{'/'.join(satellite_names)}-{'/'.join(station_names)} "
        f"全球通信时长（{len(satellites)}星×{len(config.stations)}站）"
    )
    image_path = config.paths.result_dir / image_name

    return GlobalCoverageResult(
        coverage_data=coverage_data,
        satellite_tracks=tracks,
        summary=GlobalCoverageSummary(
            satellite_count=len(satellites),
            station_count=len(config.stations),
            max_hour=float(coverage_data["TimeHour"].max(skipna=True)),
        ),
        output=OutputResult(config.paths.result_dir, image_name, image_path),
        cfg=config,
    )


def render_global_coverage(result: GlobalCoverageResult, axes=None):
    """在当前线程绘图并保存；GUI 应在 Qt 主线程调用。"""
    from stk_simulation.simulations.global_coverage.plot import plot_global_coverage
    from stk_simulation.utils.plotting import save_axes_image

    axes = plot_global_coverage(result, result.cfg, axes)
    result.output.result_dir.mkdir(parents=True, exist_ok=True)
    save_axes_image(axes, result.output.image_path)
    print(f"[保存] 图片已保存: {result.output.image_path}")
    return axes


def run_global_coverage(
    root, config: GlobalCoverageConfig, axes=None
) -> GlobalCoverageResult:
    """命令行入口：依次计算、绘图并保存。"""
    result = compute_global_coverage(root, config)
    render_global_coverage(result, axes)
    return result


def run_document_scenarios(
    root,
    base_config: GlobalCoverageConfig,
    progress: Callable[[str], None] | None = None,
) -> GlobalCoverageResult:
    """运行 Word 文档规定的三组场景，并输出海外站覆盖增量图。"""
    _report(progress, "正在从 CelesTrak 更新参考星 TLE...")
    tle = _load_reference_tle(base_config)
    jobs = (
        ("single", "single", "单星临港", "global_coverage_1sat_1station.png"),
        (
            "multi",
            "domestic",
            "三星四个国内站",
            "global_coverage_3sat_4domestic.png",
        ),
        (
            "multi",
            "all",
            "三星五站",
            "global_coverage_3sat_5station.png",
        ),
    )
    results: dict[str, GlobalCoverageResult] = {}
    image_paths: list[Path] = []
    for index, (satellite_mode, station_mode, label, image_name) in enumerate(
        jobs, start=1
    ):
        _report(progress, f"文档方案 {index}/4：{label}")
        config = copy.deepcopy(base_config)
        config.scenario.name = f"{base_config.scenario.name}_{index}"
        config.satellite_group.mode = satellite_mode
        config.stations = station_template(station_mode)
        config.output.image_name = image_name
        result = compute_global_coverage(root, config, tle=tle)
        _render_offscreen(result)
        results[station_mode] = result
        image_paths.append(result.output.image_path)

    _report(progress, "文档方案 4/4：计算墨西哥站覆盖增量")
    comparison = _coverage_increase(
        results["domestic"],
        results["all"],
        "Mexico",
        "global_coverage_3sat_mexico_increase.png",
    )
    _render_offscreen(comparison)
    image_paths.append(comparison.output.image_path)

    expanded = results["all"]
    expanded.additional_images = tuple(image_paths)
    _report(progress, "文档规定的全部全球覆盖方案已完成")
    return expanded


def run_station_gain(
    root,
    base_config: GlobalCoverageConfig,
    progress: Callable[[str], None] | None = None,
) -> GlobalCoverageResult:
    """计算当前站表中指定新增站带来的覆盖时长增益。"""
    station_name = base_config.comparison_station_name.strip()
    matches = [
        station
        for station in base_config.stations
        if station.name.casefold() == station_name.casefold()
    ]
    if len(matches) != 1:
        raise ValueError("请选择一个有效且名称唯一的增益对比站。")
    if len(base_config.stations) < 2:
        raise ValueError("计算新增站增益时，至少需要一个基准站和一个新增站。")

    _report(progress, f"正在准备 {station_name} 增益对比...")
    tle = _load_reference_tle(base_config)
    token = _file_token(station_name)
    satellite_count = 1 if base_config.satellite_group.mode == "single" else 3
    prefix = f"global_coverage_{satellite_count}sat"

    baseline_config = copy.deepcopy(base_config)
    baseline_config.scenario.name = f"{base_config.scenario.name}_Without_{token}"
    baseline_config.stations = [
        station
        for station in baseline_config.stations
        if station.name.casefold() != station_name.casefold()
    ]
    baseline_config.output.image_name = f"{prefix}_without_{token}.png"
    _report(progress, f"正在计算不含 {station_name} 的基准方案...")
    baseline = compute_global_coverage(root, baseline_config, tle=tle)

    expanded_config = copy.deepcopy(base_config)
    expanded_config.scenario.name = f"{base_config.scenario.name}_With_{token}"
    expanded_config.output.image_name = f"{prefix}_with_{token}.png"
    _report(progress, f"正在计算加入 {station_name} 后的方案...")
    expanded = compute_global_coverage(root, expanded_config, tle=tle)

    increase = _coverage_increase(
        baseline,
        expanded,
        station_name,
        f"{prefix}_{token}_increase.png",
    )
    expanded.comparison_results = (
        (f"加入前（{len(baseline_config.stations)}站）", baseline),
        (f"加入后（{len(expanded_config.stations)}站）", expanded),
        (f"增益（{station_name}）", increase),
    )
    expanded.additional_images = tuple(
        result.output.image_path for _, result in expanded.comparison_results
    )
    expanded.gain_summary = increase.gain_summary
    _report(progress, f"{station_name} 覆盖增益计算完成")
    return expanded


def _coverage_increase(
    baseline_result: GlobalCoverageResult,
    expanded: GlobalCoverageResult,
    station_name: str,
    image_name: str,
) -> GlobalCoverageResult:
    keys = ["LatitudeDeg", "LongitudeDeg"]
    baseline = baseline_result.coverage_data[keys + ["TimeHour"]].rename(
        columns={"TimeHour": "BaselineHour"}
    )
    total = expanded.coverage_data[keys + ["TimeHour"]].rename(
        columns={"TimeHour": "ExpandedHour"}
    )
    increase = baseline.merge(total, on=keys, how="outer").fillna(0.0)
    increase["TimeHour"] = np.maximum(
        increase["ExpandedHour"] - increase["BaselineHour"], 0.0
    )
    increase["TimeSec"] = increase["TimeHour"] * 3600.0

    config = copy.deepcopy(expanded.cfg)
    config.output.image_name = image_name
    config.plot.title = f"{station_name} 带来的全球通信时长增量"
    config.plot.colorbar_label = "通信时长增量 / h"
    image_path = config.paths.result_dir / config.output.image_name
    gain_summary = _gain_summary(increase, station_name)
    return GlobalCoverageResult(
        coverage_data=increase[keys + ["TimeSec", "TimeHour"]],
        satellite_tracks=expanded.satellite_tracks,
        summary=GlobalCoverageSummary(
            satellite_count=expanded.summary.satellite_count,
            station_count=expanded.summary.station_count,
            max_hour=float(increase["TimeHour"].max(skipna=True)),
        ),
        output=OutputResult(
            config.paths.result_dir, config.output.image_name, image_path
        ),
        cfg=config,
        gain_summary=gain_summary,
    )


def _gain_summary(data: pd.DataFrame, station_name: str) -> CoverageGainSummary:
    gain = data["TimeHour"].to_numpy(dtype=float)
    latitude = data["LatitudeDeg"].to_numpy(dtype=float)
    baseline = data["BaselineHour"].to_numpy(dtype=float)
    expanded = data["ExpandedHour"].to_numpy(dtype=float)
    weights = np.maximum(np.cos(np.deg2rad(latitude)), 0.0)
    positive = np.isfinite(gain) & (gain > 0.0)
    newly_covered = (baseline <= 0.0) & (expanded > 0.0)
    total_weight = float(weights.sum())
    new_percent = (
        float(weights[newly_covered].sum()) / total_weight * 100.0
        if total_weight > 0.0
        else 0.0
    )
    positive_weight = float(weights[positive].sum())
    mean_positive = (
        float(np.average(gain[positive], weights=weights[positive]))
        if positive_weight > 0.0
        else 0.0
    )
    return CoverageGainSummary(
        station_name=station_name,
        max_hour=float(np.nanmax(gain)) if gain.size else 0.0,
        mean_positive_hour=mean_positive,
        new_coverage_percent=new_percent,
        new_coverage_area_km2=510_072_000.0 * new_percent / 100.0,
    )


def _file_token(value: str) -> str:
    token = "_".join(value.strip().lower().split())
    cleaned = "".join(
        character
        for character in token
        if character.isalnum() or character == "_"
    )
    return cleaned or "station"


def _render_offscreen(result: GlobalCoverageResult) -> None:
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    figure = Figure(figsize=(14, 6.5), facecolor="white", layout="constrained")
    FigureCanvasAgg(figure)
    render_global_coverage(result, figure.add_subplot(111))
    figure.clear()


def _create_satellites(
    root, scenario, config: GlobalCoverageConfig, tle: TLEData
) -> list[Any]:
    from stk_simulation.stk.objects import STKObjects

    reference = STKObjects.create_satellite_from_tle(
        root,
        scenario,
        config.satellite.name,
        config.satellite.ssc,
        config.satellite.step,
        tle.path,
    )
    if config.satellite_group.mode == "single":
        return [reference]

    elements = derived_satellite_elements(tle, config.satellite.step)
    satellites = [reference]
    satellites.extend(
        STKObjects.create_satellite_from_elements(root, scenario, satellite_config)
        for satellite_config in elements
    )
    return satellites


def _load_reference_tle(config: GlobalCoverageConfig) -> TLEData:
    return load_latest_tle(
        config.satellite.tle_url,
        config.paths.data_dir,
        config.satellite.ssc,
    )


def _apply_interference_avoidance(
    stk_object, config: GlobalCoverageConfig
) -> None:
    if config.interference.enabled:
        from stk_simulation.stk.constraints import STKConstraints

        STKConstraints.set_sun_exclusion(
            stk_object, config.interference.angle
        )


def _read_satellite_track(
    satellite, scenario, config: GlobalCoverageConfig
) -> tuple[np.ndarray, np.ndarray]:
    plot = config.plot
    provider = satellite.DataProviders.Item("LLA State").Group.Item("Fixed")
    data = provider.Exec(scenario.StartTime, scenario.StopTime, plot.track_step)
    latitude = numeric_dataset(data, "Lat")
    longitude = numeric_dataset(data, "Lon")
    longitude = np.mod(longitude - plot.lon_range[0], 360.0) + plot.lon_range[0]
    jumps = np.concatenate(([False], np.abs(np.diff(longitude)) > 180.0))
    return np.where(jumps, np.nan, latitude), np.where(jumps, np.nan, longitude)


def _report(progress: Callable[[str], None] | None, text: str) -> None:
    if progress is not None:
        progress(text)
