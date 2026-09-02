"""单星 GPS 可见数量仿真主流程，对应 MATLAB/runGpsVisibility.m。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from simulations.global_coverage.plot_global_coverage import save_axes_image
from simulations.gps_visibility.config import GPSVisibilityConfig
from simulations.gps_visibility.plot_gps_visibility import plot_gps_visibility
from stk_api.chain import STKChain
from stk_api.constraints import STKConstraints
from stk_api.core import STKCore
from stk_api.objects import STKObjects


@dataclass
class GPSVisibilitySummary:
    gps_total: int
    min_count: int
    max_count: int
    mean_count: float
    visible_sample_count: int
    sample_count: int


@dataclass
class OutputResult:
    result_dir: Path
    image_name: str
    image_path: Path | None = None


@dataclass
class GPSVisibilityResult:
    scenario: Any
    satellite: Any
    gps_constellation: Any
    gps_satellites: list[Any]
    gps_transmitters: list[Any]
    receiver: Any
    transmitter_group: Any
    chain: Any
    gps_count_data: pd.DataFrame
    summary: GPSVisibilitySummary
    output: OutputResult
    cfg: GPSVisibilityConfig


def run_gps_visibility(
    root, config: GPSVisibilityConfig, axes=None
) -> GPSVisibilityResult:
    scenario = STKCore.create_scenario(
        root,
        config.scenario.name,
        config.scenario.start_time,
        config.scenario.stop_time,
    )
    satellite = STKObjects.create_satellite_from_tle(
        root,
        scenario,
        config.satellite.name,
        config.satellite.ssc,
        config.satellite.step,
        config.satellite.tle_file,
    )
    gps_constellation = STKObjects.load_gps_constellation(root, scenario)
    gps_satellites = STKObjects.get_gps_satellites(scenario)
    if not gps_satellites:
        raise RuntimeError("STK没有加载出可用的GPS卫星。")

    gps_transmitters = []
    for gps_satellite in gps_satellites:
        transmitter = STKObjects.create_transmitter(
            gps_satellite, config.gps.transmitter_name
        )
        transmitter.Model.Eirp = config.gps.tx_power
        transmitter.Model.Frequency = config.gps.frequency
        gps_transmitters.append(transmitter)
    print(
        f"[GPS] 已创建{len(gps_transmitters)}个发射机，"
        f"发射功率={config.gps.tx_power:.2f} dBW，"
        f"频率={config.gps.frequency:.2f} MHz"
    )

    receiver = STKObjects.create_receiver(satellite, config.receiver.name)
    STKConstraints.set_receiver_sensitivity(
        receiver, config.receiver.sensitivity
    )
    transmitter_group = STKObjects.create_constellation(
        scenario,
        config.gps.transmitter_group_name,
        gps_transmitters,
    )
    chain = STKChain.create_chain(
        scenario, config.chain.name, transmitter_group, receiver
    )
    gps_count_data = STKChain.read_number_of_accesses(
        chain, scenario, config.analysis.step
    ).rename(columns={"AccessCount": "GPSCount"})

    if not config.output.image_name:
        config.output.image_name = (
            f"gps_visibility_{config.satellite.name.lower()}.png"
        )
    config.plot.title = f"{config.satellite.name} 24小时GPS可见数量"

    result = GPSVisibilityResult(
        scenario=scenario,
        satellite=satellite,
        gps_constellation=gps_constellation,
        gps_satellites=gps_satellites,
        gps_transmitters=gps_transmitters,
        receiver=receiver,
        transmitter_group=transmitter_group,
        chain=chain,
        gps_count_data=gps_count_data,
        summary=GPSVisibilitySummary(
            gps_total=len(gps_satellites),
            min_count=int(gps_count_data["GPSCount"].min()),
            max_count=int(gps_count_data["GPSCount"].max()),
            mean_count=float(gps_count_data["GPSCount"].mean()),
            visible_sample_count=int((gps_count_data["GPSCount"] > 0).sum()),
            sample_count=len(gps_count_data),
        ),
        output=OutputResult(
            result_dir=config.paths.result_dir,
            image_name=config.output.image_name,
        ),
        cfg=config,
    )

    axes = plot_gps_visibility(result, config, axes)
    result.output.result_dir.mkdir(parents=True, exist_ok=True)
    image_path = result.output.result_dir / result.output.image_name
    save_axes_image(axes, image_path)
    result.output.image_path = image_path
    print(f"[保存] 图片已保存: {image_path}")
    return result
