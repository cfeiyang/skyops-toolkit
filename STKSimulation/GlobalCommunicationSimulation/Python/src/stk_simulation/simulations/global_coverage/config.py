"""全球通信时长仿真默认配置。"""

from __future__ import annotations

from dataclasses import dataclass, field

from stk_simulation.simulations.common import (
    NamedConfig,
    OutputConfig,
    PathsConfig,
    STKConfig,
    SatelliteConfig,
    ScenarioConfig,
    current_local_day_period,
)
from stk_simulation.simulations.global_coverage.presets import (
    StationConfig,
    station_template,
)


@dataclass
class SatelliteGroupConfig:
    mode: str = "multi"


@dataclass
class InterferenceAvoidanceConfig:
    enabled: bool = False
    angle: float = 15.0


@dataclass
class CoverageConfig(NamedConfig):
    resolution: float = 0.5
    min_elevation: float = 15.0
    grid_seed_name: str = "CoverageGridSeed"


@dataclass
class FomConfig(NamedConfig):
    min_assets: int = 1


@dataclass
class GlobalPlotConfig:
    lon_range: tuple[float, float] = (-60.0, 300.0)
    lat_range: tuple[float, float] = (-90.0, 90.0)
    center_lon: float = 120.0
    interp_step: float = 0.25
    track_step: float = 60.0
    show_contour_labels: bool = True
    lon_ticks: list[float] = field(
        default_factory=lambda: [-60, 0, 60, 120, 180, 240, 300]
    )
    lon_tick_labels: list[str] = field(
        default_factory=lambda: ["-60", "0", "60", "120", "180", "-120", "-60"]
    )
    lat_ticks: list[float] = field(default_factory=lambda: list(range(-80, 81, 20)))
    lat_tick_labels: list[str] = field(
        default_factory=lambda: ["-80", "-60", "-40", "-20", "0", "20", "40", "60", "80"]
    )
    title: str = ""
    colorbar_label: str = "通信时长 / h"


@dataclass
class GlobalCoverageConfig:
    paths: PathsConfig
    stk: STKConfig
    scenario: ScenarioConfig
    satellite: SatelliteConfig
    satellite_group: SatelliteGroupConfig
    interference: InterferenceAvoidanceConfig
    stations: list[StationConfig]
    ground_group: NamedConfig
    chain: NamedConfig
    coverage: CoverageConfig
    fom: FomConfig
    output: OutputConfig
    plot: GlobalPlotConfig
    comparison_station_name: str = ""


def config_global_coverage() -> GlobalCoverageConfig:
    paths = PathsConfig.for_simulation("global_coverage")
    start_time, stop_time = current_local_day_period()
    return GlobalCoverageConfig(
        paths=paths,
        stk=STKConfig(mode="new"),
        scenario=ScenarioConfig(
            name="GlobalCoverage",
            start_time=start_time,
            stop_time=stop_time,
        ),
        satellite=SatelliteConfig(
            name="TN01A",
            ssc=59705,
            step=60,
            tle_url=(
                "https://celestrak.org/NORAD/elements/"
                "gp.php?CATNR=59705&FORMAT=TLE"
            ),
        ),
        satellite_group=SatelliteGroupConfig(mode="multi"),
        interference=InterferenceAvoidanceConfig(),
        stations=station_template("all"),
        ground_group=NamedConfig(name="GroundStations"),
        chain=NamedConfig(name="CommChain"),
        coverage=CoverageConfig(name="GlobalCoverage"),
        fom=FomConfig(name="CommunicationTime", min_assets=1),
        output=OutputConfig(),
        plot=GlobalPlotConfig(),
    )
