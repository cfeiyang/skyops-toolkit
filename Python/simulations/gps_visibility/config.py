"""单星 GPS 可见数量仿真默认配置。"""

from __future__ import annotations

from dataclasses import dataclass

from simulations.common import (
    NamedConfig,
    OutputConfig,
    PathsConfig,
    STKConfig,
    SatelliteConfig,
    ScenarioConfig,
)


@dataclass
class GPSConfig:
    tx_power: float = 14.28
    frequency: float = 1575.42
    transmitter_name: str = "GPS_Tx"
    transmitter_group_name: str = "GPSTxConstellation"


@dataclass
class ReceiverConfig:
    name: str = "GPS_Rx"
    sensitivity: float = -172.0


@dataclass
class AnalysisConfig:
    step: float = 60.0


@dataclass
class PlotConfig:
    title: str = ""


@dataclass
class GPSVisibilityConfig:
    paths: PathsConfig
    stk: STKConfig
    scenario: ScenarioConfig
    satellite: SatelliteConfig
    gps: GPSConfig
    receiver: ReceiverConfig
    chain: NamedConfig
    analysis: AnalysisConfig
    output: OutputConfig
    plot: PlotConfig


def config_gps_visibility() -> GPSVisibilityConfig:
    paths = PathsConfig.for_simulation("gps_visibility")
    return GPSVisibilityConfig(
        paths=paths,
        stk=STKConfig(mode="new"),
        scenario=ScenarioConfig(name="GPSVisibility"),
        satellite=SatelliteConfig(
            name="TN01A",
            ssc=59705,
            step=60,
            tle_file=paths.data_dir / "TN1A_TLE_20260830.txt",
        ),
        gps=GPSConfig(),
        receiver=ReceiverConfig(),
        chain=NamedConfig(name="GPSVisibilityChain"),
        analysis=AnalysisConfig(step=60),
        output=OutputConfig(),
        plot=PlotConfig(),
    )
