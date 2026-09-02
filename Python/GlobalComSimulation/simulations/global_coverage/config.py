from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path

from setup_project import project_root
from simulations.global_coverage.templates import station_template


def config_global_coverage() -> SimpleNamespace:
    root = project_root()
    cfg = SimpleNamespace()
    cfg.paths = SimpleNamespace(
        repo_root=root,
        data_dir=root / "data",
        result_dir=root / "results" / "global_coverage",
    )
    cfg.stk = SimpleNamespace(mode="new")
    cfg.scenario = SimpleNamespace(
        name="GlobalCoverage",
        start_time="1 Sep 2026 00:00:00.000",
        stop_time="2 Sep 2026 00:00:00.000",
    )
    cfg.satellite = SimpleNamespace(
        name="TN01A",
        ssc=59705,
        step=60,
        tle_file=str(cfg.paths.data_dir / "TN1A_TLE_20260830.txt"),
    )
    cfg.satellite_group = SimpleNamespace(mode="single", name="SatelliteGroup")
    cfg.stations = station_template("single")
    cfg.ground_group = SimpleNamespace(name="GroundStations")
    cfg.chain = SimpleNamespace(name="CommChain")
    cfg.coverage = SimpleNamespace(
        name="GlobalCoverage",
        resolution=0.5,
        min_elevation=15,
        grid_seed_name="CoverageGridSeed",
    )
    cfg.fom = SimpleNamespace(name="CommunicationTime", min_assets=1)
    cfg.output = SimpleNamespace(image_name="")
    cfg.plot = _plot_defaults()
    return cfg


def _plot_defaults() -> SimpleNamespace:
    return SimpleNamespace(
        lon_range=(-60.0, 300.0),
        lat_range=(-90.0, 90.0),
        center_lon=120.0,
        interp_step=0.25,
        track_step=60,
        show_contour_labels=True,
        lon_ticks=[-60, 0, 60, 120, 180, 240, 300],
        lon_tick_labels=["-60", "0", "60", "120", "180", "-120", "-60"],
        lat_ticks=list(range(-80, 81, 20)),
        lat_tick_labels=["-80", "-60", "-40", "-20", "0", "20", "40", "60", "80"],
        title="",
    )
