"""STK 12.6 场景创建与地面站可见性计算。"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from agi.stk12.stkdesktop import STKDesktop
from agi.stk12.stkobjects import (
    AgEAccessConstraints,
    AgELeadTrailData,
    AgESTKObjectType,
    AgEVePropagatorType,
)

from stk_aer_analysis.models import (
    AERSample,
    AccessInterval,
    ScenarioRequest,
    ScenarioResult,
)
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

        satellite = self._create_satellite(root, scenario, request, tle.path)
        _report(progress, f"卫星已创建：{request.satellite_name}（{tle.name}）")

        facilities = {}
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
            facilities[station.name.casefold()] = facility
            _report(progress, f"地面站已创建：{station.name}")

        analysis_key = request.analysis_station_name.casefold()
        facility = facilities.get(analysis_key)
        if facility is None:
            raise ValueError(
                f"分析地面站不存在：{request.analysis_station_name}"
            )
        station = next(
            item
            for item in request.stations
            if item.name.casefold() == analysis_key
        )
        _report(
            progress,
            f"正在计算 {station.name} 对 {request.satellite_name} 的可见性...",
        )
        intervals, samples = self._compute_aer(
            facility,
            satellite,
            request.start_time,
            request.stop_time,
            request.aer_step_sec,
        )
        _report(
            progress,
            f"可见性计算完成：{len(intervals)} 个时段，{len(samples)} 个 AER 采样点",
        )

        root.Rewind()
        return ScenarioResult(
            scenario_name=request.scenario_name,
            satellite_name=request.satellite_name,
            tle_name=tle.name,
            station_count=len(request.stations),
            start_time=request.start_time,
            stop_time=request.stop_time,
            analysis_station_name=station.name,
            analysis_min_elevation_deg=station.min_elevation_deg,
            access_intervals=intervals,
            aer_samples=samples,
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
    def _create_satellite(
        root, scenario, request: ScenarioRequest, tle_path: Path
    ):
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
        return satellite

    @staticmethod
    def _compute_aer(
        facility,
        satellite,
        start_time: str,
        stop_time: str,
        step_sec: float,
    ) -> tuple[tuple[AccessInterval, ...], tuple[AERSample, ...]]:
        access = facility.GetAccessToObject(satellite)
        access.ComputeAccess()

        interval_result = access.DataProviders.Item("Access Data").Exec(
            start_time, stop_time
        )
        starts = _dataset_values(interval_result, "Start Time")
        stops = _dataset_values(interval_result, "Stop Time")
        durations = _dataset_values(interval_result, "Duration")

        intervals: list[AccessInterval] = []
        samples: list[AERSample] = []
        aer_provider = (
            access.DataProviders.Item("AER Data").Group.Item("Default")
        )
        elements = ["Time", "Azimuth", "Elevation", "Range"]

        for index, (interval_start, interval_stop) in enumerate(
            zip(starts, stops), start=1
        ):
            duration = (
                _as_float(durations[index - 1])
                if index <= len(durations)
                else 0.0
            )
            intervals.append(
                AccessInterval(
                    access_number=index,
                    start_time=str(interval_start),
                    stop_time=str(interval_stop),
                    duration_sec=duration,
                )
            )

            aer_result = aer_provider.ExecElements(
                interval_start,
                interval_stop,
                step_sec,
                elements,
            )
            times = _dataset_values(aer_result, "Time")
            azimuths = _dataset_values(aer_result, "Azimuth")
            elevations = _dataset_values(aer_result, "Elevation")
            ranges = _dataset_values(aer_result, "Range")
            row_count = min(
                len(times), len(azimuths), len(elevations), len(ranges)
            )
            samples.extend(
                AERSample(
                    access_number=index,
                    time=str(times[row]),
                    azimuth_deg=_as_float(azimuths[row]),
                    elevation_deg=_as_float(elevations[row]),
                    range_km=_as_float(ranges[row]),
                )
                for row in range(row_count)
            )

        return tuple(intervals), tuple(samples)


def _dataset_values(result: Any, name: str) -> list[Any]:
    try:
        values = result.DataSets.GetDataSetByName(name).GetValues()
    except Exception:
        return []
    return list(values) if values is not None else []


def _as_float(value: Any) -> float:
    return float(value)


def _report(progress: Callable[[str], None] | None, message: str) -> None:
    if progress:
        progress(message)
