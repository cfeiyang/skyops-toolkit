"""全球通信时长仿真的计算与输出流程。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from simulations.global_coverage.config import GlobalCoverageConfig
from simulations.common import OutputResult
from simulations.global_coverage.plot_global_coverage import plot_global_coverage
from simulations.global_coverage.templates import satellite_template
from stk_api.chain import STKChain
from stk_api.constraints import STKConstraints
from stk_api.core import STKCore
from stk_api.coverage import STKCoverage
from stk_api.data import instance_name, numeric_dataset
from stk_api.objects import STKObjects
from utils.plotting import save_axes_image


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
    stations = [station for station in config.stations if station.enabled]
    scenario = STKCore.create_scenario(
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

    satellite_down_node = None
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
    """在当前线程绘图并保存；GUI 应在 Tk 主线程调用。"""
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
        STKObjects.create_satellite_from_elements(root, satellite_config)
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
