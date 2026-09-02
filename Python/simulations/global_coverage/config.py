"""全球通信时长仿真默认配置。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from setup_project import project_root
from simulations.global_coverage.templates import StationConfig, station_template


@dataclass
class PathsConfig:
    repo_root: Path
    data_dir: Path
    result_dir: Path


@dataclass
class STKConfig:
    mode: str = "new"


@dataclass
class ScenarioConfig:
    name: str = "GlobalCoverage"
    start_time: str = "1 Sep 2026 00:00:00.000"
    stop_time: str = "2 Sep 2026 00:00:00.000"


@dataclass
class SatelliteConfig:
    name: str
    ssc: int
    step: float
    tle_file: Path


@dataclass
class NamedConfig:
    name: str


@dataclass
class SatelliteGroupConfig(NamedConfig):
    mode: str = "single"


@dataclass
class CoverageConfig(NamedConfig):
    resolution: float = 0.5
    min_elevation: float = 15.0
    grid_seed_name: str = "CoverageGridSeed"


@dataclass
class FomConfig(NamedConfig):
    min_assets: int = 1


@dataclass
class OutputConfig:
    image_name: str = ""


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


@dataclass
class GlobalCoverageConfig:
    paths: PathsConfig
    stk: STKConfig
    scenario: ScenarioConfig
    satellite: SatelliteConfig
    satellite_group: SatelliteGroupConfig
    stations: list[StationConfig]
    ground_group: NamedConfig
    chain: NamedConfig
    coverage: CoverageConfig
    fom: FomConfig
    output: OutputConfig
    plot: GlobalPlotConfig


def config_global_coverage() -> GlobalCoverageConfig:
    root = project_root()
    paths = PathsConfig(
        repo_root=root,
        data_dir=root / "data",
        result_dir=root / "results" / "global_coverage",
    )
    return GlobalCoverageConfig(
        paths=paths,
        stk=STKConfig(mode="new"),
        scenario=ScenarioConfig(),
        satellite=SatelliteConfig(
            name="TN01A",
            ssc=59705,
            step=60,
            tle_file=paths.data_dir / "TN1A_TLE_20260830.txt",
        ),
        satellite_group=SatelliteGroupConfig(name="SatelliteGroup", mode="single"),
        stations=station_template("single"),
        ground_group=NamedConfig(name="GroundStations"),
        chain=NamedConfig(name="CommChain"),
        coverage=CoverageConfig(name="GlobalCoverage"),
        fom=FomConfig(name="CommunicationTime", min_assets=1),
        output=OutputConfig(),
        plot=GlobalPlotConfig(),
    )
