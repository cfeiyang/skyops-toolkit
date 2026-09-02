from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from stk_api.chain import STKChain
from stk_api.constraints import STKConstraints
from stk_api.core import STKCore
from stk_api.objects import STKObjectsAPI as STKObjects
from stk_api.typelib import load_stk_modules, qi
from simulations.global_coverage.plot import save_axes_image
from simulations.gps_visibility.plot import plot_gps_visibility


def run_gps_visibility(root, cfg, ax=None):
    stk_objects, _ = load_stk_modules()
    scenario = STKCore.create_scenario(
        root, cfg.scenario.name, cfg.scenario.start_time, cfg.scenario.stop_time
    )
    satellite = STKObjects.create_satellite_from_tle(
        root,
        scenario,
        cfg.satellite.name,
        cfg.satellite.ssc,
        cfg.satellite.step,
        cfg.satellite.tle_file,
    )
    gps_constellation = STKObjects.load_gps_constellation(root, scenario)
    gps_satellites = STKObjects.get_gps_satellites(scenario)
    if not gps_satellites:
        raise RuntimeError("STK没有加载出可用的GPS卫星。")

    gps_transmitters = []
    for gps_sat in gps_satellites:
        transmitter = STKObjects.create_transmitter(gps_sat, cfg.gps.transmitter_name)
        model = qi(transmitter.Model, stk_objects.IAgTransmitterModelSimple)
        model.Eirp = cfg.gps.tx_power
        model.Frequency = cfg.gps.frequency
        gps_transmitters.append(transmitter)
    print(
        f"[GPS] 已创建{len(gps_transmitters)}个发射机，"
        f"发射功率={cfg.gps.tx_power:.2f} dBW，频率={cfg.gps.frequency:.2f} MHz"
    )

    receiver = STKObjects.create_receiver(satellite, cfg.receiver.name)
    STKConstraints.set_receiver_sensitivity(receiver, cfg.receiver.sensitivity)
    transmitter_group = STKObjects.create_constellation(
        scenario, cfg.gps.transmitter_group_name, gps_transmitters
    )
    chain = STKChain.create_chain(scenario, cfg.chain.name, transmitter_group, receiver)
    gps_count_data = STKChain.read_number_of_accesses(chain, scenario, cfg.analysis.step)
    gps_count_data = gps_count_data.rename(columns={"AccessCount": "GPSCount"})

    if not cfg.output.image_name:
        cfg.output.image_name = f"gps_visibility_{cfg.satellite.name.lower()}.png"
    cfg.plot.title = f"{cfg.satellite.name} 24小时GPS可见数量"

    result = SimpleNamespace(
        scenario=scenario,
        satellite=satellite,
        gps_constellation=gps_constellation,
        gps_satellites=gps_satellites,
        gps_transmitters=gps_transmitters,
        receiver=receiver,
        transmitter_group=transmitter_group,
        chain=chain,
        gps_count_data=gps_count_data,
        summary=SimpleNamespace(
            gps_total=len(gps_satellites),
            min_count=int(gps_count_data["GPSCount"].min()),
            max_count=int(gps_count_data["GPSCount"].max()),
            mean_count=float(gps_count_data["GPSCount"].mean()),
            visible_sample_count=int((gps_count_data["GPSCount"] > 0).sum()),
            sample_count=len(gps_count_data),
        ),
        output=SimpleNamespace(
            result_dir=Path(cfg.paths.result_dir),
            image_name=cfg.output.image_name,
        ),
        cfg=cfg,
    )

    ax = plot_gps_visibility(result, cfg, ax)
    result.output.result_dir.mkdir(parents=True, exist_ok=True)
    image_path = result.output.result_dir / cfg.output.image_name
    save_axes_image(ax, image_path)
    result.output.image_path = image_path
    print(f"[保存] 图片已保存: {image_path}")
    return result
