"""单星 GPS 可见数量仿真的计算与输出流程。"""

from __future__ import annotations

from dataclasses import dataclass
import pandas as pd

from simulations.common import OutputResult
from simulations.gps_visibility.config import GPSVisibilityConfig
from simulations.gps_visibility.plot_gps_visibility import plot_gps_visibility
from stk_api.chain import STKChain
from stk_api.constraints import STKConstraints
from stk_api.core import STKCore
from stk_api.objects import STKObjects
from utils.plotting import save_axes_image


@dataclass
class GPSVisibilitySummary:
    gps_total: int
    min_count: int
    max_count: int
    mean_count: float
    visible_sample_count: int
    sample_count: int


@dataclass
class GPSVisibilityResult:
    gps_count_data: pd.DataFrame
    summary: GPSVisibilitySummary
    output: OutputResult
    cfg: GPSVisibilityConfig


def compute_gps_visibility(root, config: GPSVisibilityConfig) -> GPSVisibilityResult:
    """创建 STK 场景并提取 GPS 可见数量，不操作 GUI。"""
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
        raise RuntimeError("STK 没有加载出可用的 GPS 卫星。")

    gps_transmitters = []
    for gps_satellite in gps_satellites:
        transmitter = STKObjects.create_transmitter(
            gps_satellite, config.gps.transmitter_name
        )
        transmitter.Model.Eirp = config.gps.tx_power
        transmitter.Model.Frequency = config.gps.frequency
        gps_transmitters.append(transmitter)
    print(
        f"[GPS] 已创建 {len(gps_transmitters)} 个发射机，"
        f"发射功率={config.gps.tx_power:.2f} dBW，"
        f"频率={config.gps.frequency:.2f} MHz"
    )

    receiver = STKObjects.create_receiver(satellite, config.receiver.name)
    STKConstraints.set_receiver_sensitivity(receiver, config.receiver.sensitivity)
    transmitter_group = STKObjects.create_constellation(
        scenario, config.gps.transmitter_group_name, gps_transmitters
    )
    chain = STKChain.create_chain(
        scenario, config.chain.name, transmitter_group, receiver
    )
    count_data = STKChain.read_number_of_accesses(
        chain, scenario, config.analysis.step
    ).rename(columns={"AccessCount": "GPSCount"})

    image_name = config.output.image_name or (
        f"gps_visibility_{config.satellite.name.lower()}.png"
    )
    config.output.image_name = image_name
    config.plot.title = f"{config.satellite.name} 24 小时 GPS 可见数量"
    image_path = config.paths.result_dir / image_name

    return GPSVisibilityResult(
        gps_count_data=count_data,
        summary=GPSVisibilitySummary(
            gps_total=len(gps_satellites),
            min_count=int(count_data["GPSCount"].min()),
            max_count=int(count_data["GPSCount"].max()),
            mean_count=float(count_data["GPSCount"].mean()),
            visible_sample_count=int((count_data["GPSCount"] > 0).sum()),
            sample_count=len(count_data),
        ),
        output=OutputResult(config.paths.result_dir, image_name, image_path),
        cfg=config,
    )


def render_gps_visibility(result: GPSVisibilityResult, axes=None):
    axes = plot_gps_visibility(result, result.cfg, axes)
    result.output.result_dir.mkdir(parents=True, exist_ok=True)
    save_axes_image(axes, result.output.image_path)
    print(f"[保存] 图片已保存: {result.output.image_path}")
    return axes


def run_gps_visibility(
    root, config: GPSVisibilityConfig, axes=None
) -> GPSVisibilityResult:
    result = compute_gps_visibility(root, config)
    render_gps_visibility(result, axes)
    return result
