"""全球通信时长仿真的计算与输出流程。"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np
import pandas as pd
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from stk_simulation.simulations.common import OutputResult
from stk_simulation.simulations.global_coverage.config import GlobalCoverageConfig
from stk_simulation.simulations.global_coverage.plot import plot_global_coverage
from stk_simulation.simulations.global_coverage.presets import (
    satellite_template,
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


def compute_global_coverage(
    root, config: GlobalCoverageConfig
) -> GlobalCoverageResult:
    """创建 STK 场景并提取绘图所需的全部数值，不操作 GUI。"""
    stations = config.stations
    scenario = STKSession.create_scenario(
        root,
        config.scenario.name,
        config.scenario.start_time,
        config.scenario.stop_time,
    )
    satellites = _create_satellites(root, scenario, config)
    satellite_node = STKObjects.create_satellite_group(
        scenario, config.satellite_group.name, satellites
    )

    facilities = []
    for station in stations:
        facility = STKObjects.create_facility(
            scenario, station.name, station.lat, station.lon, station.alt
        )
        STKConstraints.set_min_elevation(facility, station.min_elevation)
        facilities.append(facility)

    ground_node = STKObjects.create_ground_group(
        scenario, config.ground_group.name, facilities
    )

    if config.satellite_group.mode == "single":
        chain = STKChain.create_sat_ground_chain(
            scenario, config.chain.name, ground_node, satellite_node
        )
    else:
        satellite_down_node = STKObjects.create_satellite_group(
            scenario, f"{config.satellite_group.name}_Down", satellites
        )
        chain = STKChain.create_sat_ground_chain_with_isl(
            scenario,
            config.chain.name,
            ground_node,
            satellite_node,
            satellite_down_node,
        )

    grid_seed = STKCoverage.create_coverage_grid_seed(
        scenario,
        config.coverage.grid_seed_name,
        config.coverage.min_elevation,
    )
    coverage = STKCoverage.create_global_coverage(
        scenario,
        config.coverage.name,
        config.coverage.resolution,
        chain,
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
    station_names = [station.name for station in stations]
    image_name = config.output.image_name or (
        f"global_coverage_{len(satellites)}sat_{len(stations)}station.png"
    )
    config.output.image_name = image_name
    config.plot.title = (
        f"{'/'.join(satellite_names)}-{'/'.join(station_names)} "
        f"全球通信时长（{len(satellites)}星×{len(stations)}站）"
    )
    image_path = config.paths.result_dir / image_name

    return GlobalCoverageResult(
        coverage_data=coverage_data,
        satellite_tracks=tracks,
        summary=GlobalCoverageSummary(
            satellite_count=len(satellites),
            station_count=len(stations),
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
    """命令行兼容入口：依次计算、绘图并保存。"""
    result = compute_global_coverage(root, config)
    render_global_coverage(result, axes)
    return result


def run_global_coverage_batch(
    root,
    base_config: GlobalCoverageConfig,
    progress: Callable[[str], None] | None = None,
) -> GlobalCoverageResult:
    """依次运行单/三星与一至四站的八组预设方案。"""
    combinations = [
        (satellite_mode, station_mode, satellite_label, station_label)
        for satellite_mode, satellite_label in (("single", "单星"), ("multi", "多星"))
        for station_mode, station_label in (
            ("single", "单站"),
            ("two", "双站"),
            ("three", "三站"),
            ("four", "四站"),
        )
    ]
    last_result = None
    for index, (satellite_mode, station_mode, satellite_label, station_label) in enumerate(
        combinations, start=1
    ):
        if progress is not None:
            progress(f"自动仿真 {index}/8：{satellite_label}{station_label}")
        config = copy.deepcopy(base_config)
        config.satellite_group.mode = satellite_mode
        config.stations = station_template(station_mode)
        config.output.image_name = ""
        last_result = compute_global_coverage(root, config)
        _render_offscreen(last_result)
        if root.CurrentScenario is not None:
            root.CloseScenario()

    if last_result is None:
        raise RuntimeError("没有可执行的全球通信时长预设方案。")
    return last_result


def _render_offscreen(result: GlobalCoverageResult) -> None:
    figure = Figure(figsize=(14, 6.5), facecolor="white", layout="constrained")
    FigureCanvasAgg(figure)
    render_global_coverage(result, figure.add_subplot(111))
    figure.clear()


def _create_satellites(root, scenario, config: GlobalCoverageConfig) -> list[Any]:
    if config.satellite_group.mode == "single":
        return [
            STKObjects.create_satellite_from_tle(
                root,
                scenario,
                config.satellite.name,
                config.satellite.ssc,
                config.satellite.step,
                config.satellite.tle_file,
            )
        ]
    return [
        STKObjects.create_satellite_from_elements(
            root, scenario, satellite_config
        )
        for satellite_config in satellite_template(config.satellite_group.mode)
    ]


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
