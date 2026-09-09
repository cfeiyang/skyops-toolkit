"""STK 12.6 会话与场景对象创建。"""

from __future__ import annotations

from collections.abc import Callable

from agi.stk12.stkdesktop import STKDesktop
from agi.stk12.stkobjects import (
    AgEAccessConstraints,
    AgELeadTrailData,
    AgESTKObjectType,
    AgEVePropagatorType,
)

from stk_aer_analysis.models import ScenarioRequest, ScenarioResult
from stk_aer_analysis.paths import application_root
from stk_aer_analysis.tle import load_latest_tle


class STKService:
    def __init__(self) -> None:
        self._application = None
        self._root = None
        self._mode: str | None = None

    def create_scenario(
        self,
        request: ScenarioRequest,
        progress: Callable[[str], None] | None = None,
    ) -> ScenarioResult:
        _report(progress, f"正在获取卫星 {request.satellite_ssc} 最新 TLE...")
        tle = load_latest_tle(
            request.tle_url,
            application_root() / "data",
            request.satellite_ssc,
        )

        _report(progress, "正在连接 STK 12...")
        root = self._connect(request.stk_mode)
        self._set_units(root)

        if root.CurrentScenario is not None:
            root.CloseScenario()
        root.NewScenario(request.scenario_name)
        scenario = root.CurrentScenario
        scenario.SetTimePeriod(request.start_time, request.stop_time)
        root.Rewind()
        _report(progress, f"场景已创建：{request.scenario_name}")

        self._create_satellite(root, scenario, request, tle.path)
        _report(progress, f"卫星已创建：{request.satellite_name}（{tle.name}）")

        for station in request.stations:
            facility = scenario.Children.New(
                AgESTKObjectType.eFacility, station.name
            )
            facility.Position.AssignGeodetic(
                station.latitude_deg,
                station.longitude_deg,
                station.altitude_m / 1000.0,
            )
            constraint = facility.AccessConstraints.AddConstraint(
                AgEAccessConstraints.eCstrElevationAngle
            )
            constraint.EnableMin = True
            constraint.Min = station.min_elevation_deg
            _report(progress, f"地面站已创建：{station.name}")

        root.Rewind()
        return ScenarioResult(
            scenario_name=request.scenario_name,
            satellite_name=request.satellite_name,
            tle_name=tle.name,
            station_count=len(request.stations),
            start_time=request.start_time,
            stop_time=request.stop_time,
        )

    def release(self) -> None:
        self._root = None
        self._application = None
        self._mode = None

    def _connect(self, mode: str):
        normalized = str(mode).lower()
        if self._root is not None and normalized == self._mode:
            return self._root
        if normalized == "new":
            application = STKDesktop.StartApplication(
                visible=True, userControl=True
            )
        elif normalized == "running":
            application = STKDesktop.AttachToApplication()
        else:
            raise ValueError("STK 连接方式必须是 new 或 running。")
        self._application = application
        self._root = application.Root
        self._mode = normalized
        return self._root

    @staticmethod
    def _set_units(root) -> None:
        preferences = root.UnitPreferences
        preferences.Item("AngleUnit").SetCurrentUnit("deg")
        preferences.Item("DistanceUnit").SetCurrentUnit("km")
        preferences.Item("TimeUnit").SetCurrentUnit("sec")
        preferences.Item("DateFormat").SetCurrentUnit("UTCG")

    @staticmethod
    def _create_satellite(root, scenario, request: ScenarioRequest, tle_path) -> None:
        satellite = scenario.Children.New(
            AgESTKObjectType.eSatellite, request.satellite_name
        )
        satellite.SetPropagatorType(AgEVePropagatorType.ePropagatorSGP4)
        propagator = satellite.Propagator
        analysis_interval = root.CurrentScenario.Vgt.EventIntervals.Item(
            "AnalysisInterval"
        )
        propagator.EphemerisInterval.SetImplicitInterval(analysis_interval)
        propagator.Step = request.propagation_step_sec
        propagator.CommonTasks.AddSegsFromFile(
            str(request.satellite_ssc), str(tle_path)
        )
        propagator.Propagate()
        ground_track = satellite.Graphics.PassData.GroundTrack
        ground_track.SetLeadDataType(AgELeadTrailData.eDataAll)
        ground_track.SetTrailSameAsLead()


def _report(progress: Callable[[str], None] | None, message: str) -> None:
    if progress:
        progress(message)

