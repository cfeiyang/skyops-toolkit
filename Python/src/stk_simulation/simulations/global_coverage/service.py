"""全球通信时长仿真的计算、文档方案和输出流程。"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from stk_simulation.simulations.common import OutputResult
from stk_simulation.simulations.global_coverage.config import GlobalCoverageConfig
from stk_simulation.simulations.global_coverage.plot import plot_global_coverage
from stk_simulation.simulations.global_coverage.presets import (
    satellites_from_reference_tle,
    station_template,
)
from stk_simulation.stk.chain import STKChain
from stk_simulation.stk.constraints import STKConstraints
from stk_simulation.stk.coverage import STKCoverage
from stk_simulation.stk.data import instance_name, numeric_dataset
from stk_simulation.stk.objects import STKObjects
from stk_simulation.stk.session import STKSession
from stk_simulation.utils.plotting import save_axes_image


@dataclass
class GlobalCoverageSummary:
    satellite_count: int
    station_count: int
    max_hour: float


@dataclass
class GlobalCoverageResult:
    coverage_data: pd.DataFrame
    satellite_tracks: list[tuple[np.ndarray, np.ndarray]]
    summary: GlobalCoverageSummary
    output: OutputResult
    cfg: GlobalCoverageConfig
    additional_images: tuple[Path, ...] = field(default_factory=tuple)


def compute_global_coverage(
    root, config: GlobalCoverageConfig
) -> GlobalCoverageResult:
    """创建 STK 场景并提取绘图所需的全部数值，不操作 GUI。"""
    scenario = STKSession.create_scenario(
        root,
        config.scenario.name,
        config.scenario.start_time,
        config.scenario.stop_time,
    )
    satellites = _create_satellites(root, scenario, config)

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
        result = compute_global_coverage(root, config)
        _render_offscreen(result)
        results[station_mode] = result
        image_paths.append(result.output.image_path)

    _report(progress, "文档方案 4/4：计算墨西哥站覆盖增量")
    comparison = _coverage_increase(results["domestic"], results["all"])
    _render_offscreen(comparison)
    image_paths.append(comparison.output.image_path)

    expanded = results["all"]
    expanded.additional_images = tuple(image_paths)
    _report(progress, "文档规定的全部全球覆盖方案已完成")
    return expanded


def _coverage_increase(
    domestic: GlobalCoverageResult,
    expanded: GlobalCoverageResult,
) -> GlobalCoverageResult:
    keys = ["LatitudeDeg", "LongitudeDeg"]
    baseline = domestic.coverage_data[keys + ["TimeHour"]].rename(
        columns={"TimeHour": "DomesticHour"}
    )
    total = expanded.coverage_data[keys + ["TimeHour"]].rename(
        columns={"TimeHour": "ExpandedHour"}
    )
    increase = baseline.merge(total, on=keys, how="outer").fillna(0.0)
    increase["TimeHour"] = np.maximum(
        increase["ExpandedHour"] - increase["DomesticHour"], 0.0
    )
    increase["TimeSec"] = increase["TimeHour"] * 3600.0

    config = copy.deepcopy(expanded.cfg)
    config.output.image_name = "global_coverage_3sat_mexico_increase.png"
    config.plot.title = "墨西哥规划站带来的三星全球通信时长增量"
    config.plot.colorbar_label = "通信时长增量 / h"
    image_path = config.paths.result_dir / config.output.image_name
    return GlobalCoverageResult(
        coverage_data=increase[keys + ["TimeSec", "TimeHour"]],
        satellite_tracks=expanded.satellite_tracks,
        summary=GlobalCoverageSummary(
            satellite_count=3,
            station_count=5,
            max_hour=float(increase["TimeHour"].max(skipna=True)),
        ),
        output=OutputResult(
            config.paths.result_dir, config.output.image_name, image_path
        ),
        cfg=config,
    )


def _render_offscreen(result: GlobalCoverageResult) -> None:
    figure = Figure(figsize=(14, 6.5), facecolor="white", layout="constrained")
    FigureCanvasAgg(figure)
    render_global_coverage(result, figure.add_subplot(111))
    figure.clear()


def _create_satellites(
    root, scenario, config: GlobalCoverageConfig
) -> list[Any]:
    reference = STKObjects.create_satellite_from_tle(
        root,
        scenario,
        config.satellite.name,
        config.satellite.ssc,
        config.satellite.step,
        config.satellite.tle_file,
    )
    if config.satellite_group.mode == "single":
        return [reference]

    elements = satellites_from_reference_tle(
        config.satellite.tle_file,
        config.satellite.ssc,
        config.satellite.name,
        config.satellite.step,
    )
    satellites = [reference]
    satellites.extend(
        STKObjects.create_satellite_from_elements(root, scenario, satellite_config)
        for satellite_config in elements[1:]
    )
    return satellites


def _apply_interference_avoidance(
    stk_object, config: GlobalCoverageConfig
) -> None:
    if config.interference.enabled:
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
