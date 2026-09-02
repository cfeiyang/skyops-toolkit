"""全球通信时长仿真主流程，对应 MATLAB/runGlobalCoverage.m。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from simulations.global_coverage.config import GlobalCoverageConfig
from simulations.global_coverage.plot_global_coverage import (
    plot_global_coverage,
    save_axes_image,
)
from simulations.global_coverage.templates import satellite_template
from stk_api.chain import STKChain
from stk_api.constraints import STKConstraints
from stk_api.core import STKCore
from stk_api.coverage import STKCoverage
from stk_api.data import instance_name
from stk_api.objects import STKObjects


@dataclass
class GlobalCoverageSummary:
    satellite_count: int
    station_count: int
    max_hour: float


@dataclass
class OutputResult:
    result_dir: Path
    image_name: str
    image_path: Path | None = None


@dataclass
class GlobalCoverageResult:
    scenario: Any
    satellites: list[Any]
    satellite_node: Any
    satellite_down_node: Any
    facilities: list[Any]
    ground_node: Any
    chain: Any
    coverage_grid_seed: Any
    coverage: Any
    fom: Any
    coverage_data: pd.DataFrame
    summary: GlobalCoverageSummary
    output: OutputResult
    cfg: GlobalCoverageConfig


def run_global_coverage(
    root, config: GlobalCoverageConfig, axes=None
) -> GlobalCoverageResult:
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

    satellite_names = [instance_name(satellite) for satellite in satellites]
    station_names = [station.name for station in stations]
    base_name = f"global_coverage_{len(satellites)}sat_{len(stations)}station"
    if not config.output.image_name:
        config.output.image_name = f"{base_name}.png"

    config.plot.title = (
        f"{'/'.join(satellite_names)}-{'/'.join(station_names)} "
        f"全球通信时长 ({len(satellites)}星{len(stations)}站)"
    )

    result = GlobalCoverageResult(
        scenario=scenario,
        satellites=satellites,
        satellite_node=satellite_node,
        satellite_down_node=satellite_down_node,
        facilities=facilities,
        ground_node=ground_node,
        chain=chain,
        coverage_grid_seed=grid_seed,
        coverage=coverage,
        fom=fom,
        coverage_data=coverage_data,
        summary=GlobalCoverageSummary(
            satellite_count=len(satellites),
            station_count=len(stations),
            max_hour=float(coverage_data["TimeHour"].max(skipna=True)),
        ),
        output=OutputResult(
            result_dir=config.paths.result_dir,
            image_name=config.output.image_name,
        ),
        cfg=config,
    )

    axes = plot_global_coverage(result, config, axes)
    result.output.result_dir.mkdir(parents=True, exist_ok=True)
    image_path = result.output.result_dir / result.output.image_name
    save_axes_image(axes, image_path)
    result.output.image_path = image_path
    print(f"[保存] 图片已保存: {image_path}")
    return result


def _create_satellites(root, scenario, config: GlobalCoverageConfig) -> list[Any]:
    if config.satellite_group.mode == "single":
        satellite = STKObjects.create_satellite_from_tle(
            root,
            scenario,
            config.satellite.name,
            config.satellite.ssc,
            config.satellite.step,
            config.satellite.tle_file,
        )
        return [satellite]

    return [
        STKObjects.create_satellite_from_elements(root, scenario, satellite_config)
        for satellite_config in satellite_template(config.satellite_group.mode)
    ]
