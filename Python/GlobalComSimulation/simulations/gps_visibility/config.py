from __future__ import annotations

from types import SimpleNamespace

from setup_project import project_root


def config_gps_visibility() -> SimpleNamespace:
    root = project_root()
    cfg = SimpleNamespace()
    cfg.paths = SimpleNamespace(
        repo_root=root,
        data_dir=root / "data",
        result_dir=root / "results" / "gps_visibility",
    )
    cfg.stk = SimpleNamespace(mode="new")
    cfg.scenario = SimpleNamespace(
        name="GPSVisibility",
        start_time="1 Sep 2026 00:00:00.000",
        stop_time="2 Sep 2026 00:00:00.000",
    )
    cfg.satellite = SimpleNamespace(
        name="TN01A",
        ssc=59705,
        step=60,
        tle_file=str(cfg.paths.data_dir / "TN1A_TLE_20260830.txt"),
    )
    cfg.gps = SimpleNamespace(
        tx_power=14.28,
        frequency=1575.42,
        transmitter_name="GPS_Tx",
        transmitter_group_name="GPSTxConstellation",
    )
    cfg.receiver = SimpleNamespace(name="GPS_Rx", sensitivity=-172)
    cfg.chain = SimpleNamespace(name="GPSVisibilityChain")
    cfg.analysis = SimpleNamespace(step=60)
    cfg.output = SimpleNamespace(image_name="")
    cfg.plot = SimpleNamespace(title="")
    return cfg
