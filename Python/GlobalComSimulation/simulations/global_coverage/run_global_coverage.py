from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from stk_api.chain import STKChain
from stk_api.constraints import STKConstraints
from stk_api.core import STKCore
from stk_api.coverage import STKCoverage
from stk_api.objects import STKObjectsAPI as STKObjects
from stk_api.typelib import instance_name
from simulations.global_coverage.plot import plot_global_coverage, save_axes_image
from simulations.global_coverage.templates import satellite_template


def run_global_coverage(root, cfg, ax=None):
    stations = [s for s in cfg.stations if s.get("enabled", True)]
    scenario = STKCore.create_scenario(
        root, cfg.scenario.name, cfg.scenario.start_time, cfg.scenario.stop_time
    )
    satellites = _create_satellites(root, scenario, cfg)
    satellite_node = STKObjects.create_satellite_group(
        scenario, cfg.satellite_group.name, satellites
    )

    facilities = []
    for station in stations:
        facility = STKObjects.create_facility(
            scenario, station["name"], station["lat"], station["lon"], station["alt"]
        )
        STKConstraints.set_min_elevation(facility, station["min_elevation"])
        facilities.append(facility)

    ground_node = STKObjects.create_ground_group(scenario, cfg.ground_group.name, facilities)

    sat_down_node = None
    if cfg.satellite_group.mode == "single":
        chain = STKChain.create_sat_ground_chain(
            scenario, cfg.chain.name, ground_node, satellite_node
        )
    else:
        sat_down_node = STKObjects.create_satellite_group(
            scenario, cfg.satellite_group.name + "_Down", satellites
        )
        chain = STKChain.create_sat_ground_chain_with_isl(
            scenario, cfg.chain.name, ground_node, satellite_node, sat_down_node
        )

    grid_seed = STKCoverage.create_coverage_grid_seed(
        scenario, cfg.coverage.grid_seed_name, cfg.coverage.min_elevation
    )
    coverage = STKCoverage.create_global_coverage(
        scenario, cfg.coverage.name, cfg.coverage.resolution, chain, grid_seed
    )
    fom = STKCoverage.create_coverage_time_fom(coverage, cfg.fom.name, cfg.fom.min_assets)
    coverage_data = STKCoverage.read_coverage_time(fom)

    satellite_names = [instance_name(sat) for sat in satellites]
    station_names = [s["name"] for s in stations]
    base_name = f"global_coverage_{len(satellites)}sat_{len(stations)}station"
    if not cfg.output.image_name:
        cfg.output.image_name = base_name + ".png"
    cfg.plot.title = (
        f"{'/'.join(satellite_names)}-{ '/'.join(station_names) } "
        f"全球通信时长 ({len(satellites)}星{len(stations)}站)"
    )

    result = SimpleNamespace(
        scenario=scenario,
        satellites=satellites,
        satellite_node=satellite_node,
        satellite_down_node=sat_down_node,
        facilities=facilities,
        ground_node=ground_node,
        chain=chain,
        coverage_grid_seed=grid_seed,
        coverage=coverage,
        fom=fom,
        coverage_data=coverage_data,
        summary=SimpleNamespace(
            satellite_count=len(satellites),
            station_count=len(stations),
            max_hour=float(coverage_data["TimeHour"].max(skipna=True)),
        ),
        output=SimpleNamespace(
            result_dir=Path(cfg.paths.result_dir),
            image_name=cfg.output.image_name,
        ),
        cfg=cfg,
    )

    ax = plot_global_coverage(result, cfg, ax)
    result.output.result_dir.mkdir(parents=True, exist_ok=True)
    image_path = result.output.result_dir / cfg.output.image_name
    save_axes_image(ax, image_path)
    result.output.image_path = image_path
    print(f"[保存] 图片已保存: {image_path}")
    return result


def _create_satellites(root, scenario, cfg):
    if cfg.satellite_group.mode == "single":
        satellite = STKObjects.create_satellite_from_tle(
            root,
            scenario,
            cfg.satellite.name,
            cfg.satellite.ssc,
            cfg.satellite.step,
            cfg.satellite.tle_file,
        )
        return [satellite]
    satellites = []
    for sat_cfg in satellite_template(cfg.satellite_group.mode):
        satellites.append(STKObjects.create_satellite_from_elements(root, scenario, sat_cfg))
    return satellites
