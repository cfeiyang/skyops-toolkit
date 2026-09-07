"""STK Facility、Satellite 和 Constellation 创建。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agi.stk12.stkobjects import (
    AgELeadTrailData,    # type: ignore
    AgESTKObjectType,    # type: ignore
    AgEVePropagatorType, # type: ignore
)

from stk_simulation.stk.data import instance_name


class STKObjects:
    @staticmethod
    def create_facility(
        scenario, name: str, latitude: float, longitude: float, altitude: float
    ):
        facility = scenario.Children.New(AgESTKObjectType.eFacility, name)
        facility.Position.AssignGeodetic(latitude, longitude, altitude)
        print(f"[地面站] 成功创建 Facility: {name}")
        return facility

    @staticmethod
    def create_satellite_from_tle(
        root,
        scenario,
        name: str,
        ssc: int,
        step: float,
        tle_file: str | Path,
    ):
        tle_path = Path(tle_file)
        if not tle_path.is_file():
            raise FileNotFoundError(f"TLE 文件不存在：{tle_path}")

        satellite = scenario.Children.New(AgESTKObjectType.eSatellite, name)
        satellite.SetPropagatorType(AgEVePropagatorType.ePropagatorSGP4)
        propagator = satellite.Propagator
        analysis_interval = root.CurrentScenario.Vgt.EventIntervals.Item(
            "AnalysisInterval"
        )
        propagator.EphemerisInterval.SetImplicitInterval(analysis_interval)
        propagator.Step = step
        propagator.CommonTasks.AddSegsFromFile(str(ssc), str(tle_path))
        propagator.Propagate()

        STKObjects._set_full_ground_track(satellite)
        print(f"[卫星] 成功创建 {name} (SGP4, SSC={ssc}, Object Model)")
        print("[卫星] 2D Ground Track 已设置为完整 Ephemeris 范围")
        return satellite

    @staticmethod
    def create_satellite_from_elements(root, scenario, satellite_config: Any):
        root.UnitPreferences.Item("AngleUnit").SetCurrentUnit("deg")
        root.UnitPreferences.Item("TimeUnit").SetCurrentUnit("sec")
        root.UnitPreferences.Item("DateFormat").SetCurrentUnit("UTCG")

        satellite = scenario.Children.New(
            AgESTKObjectType.eSatellite, satellite_config.name
        )
        satellite.SetPropagatorType(AgEVePropagatorType.ePropagatorSGP4)
        propagator = satellite.Propagator
        analysis_interval = root.CurrentScenario.Vgt.EventIntervals.Item(
            "AnalysisInterval"
        )
        propagator.EphemerisInterval.SetImplicitInterval(analysis_interval)
        propagator.Step = satellite_config.step
        propagator.AutoUpdateEnabled = False

        propagator.Segments.SSCNumber = str(satellite_config.ssc)
        segment = propagator.Segments.AddSeg()
        segment.Epoch = satellite_config.epoch
        segment.MeanMotion = satellite_config.mean_motion
        segment.Eccentricity = satellite_config.eccentricity
        segment.Inclination = satellite_config.inclination
        segment.ArgOfPerigee = satellite_config.arg_perigee
        segment.RAAN = satellite_config.raan
        segment.MeanAnomaly = satellite_config.mean_anomaly
        propagator.Propagate()

        STKObjects._set_full_ground_track(satellite)
        print(f"[卫星] {satellite_config.name} 创建成功")
        return satellite

    @staticmethod
    def create_ground_group(scenario, name: str, facilities: list[Any]):
        if not facilities:
            raise ValueError("STKObjects.create_ground_group: facilities 不能为空。")
        if len(facilities) == 1:
            print(f"[地面站] 成功创建 Single station: {instance_name(facilities[0])}")
            return facilities[0]

        group = STKObjects.create_constellation(scenario, name, facilities)
        print(f"[地面站] 成功创建 {len(facilities)} stations, logic = ANY OF")
        return group

    @staticmethod
    def create_constellation(scenario, name: str, objects: list[Any]):
        if not objects:
            raise ValueError("STKObjects.create_constellation: objects 不能为空。")

        constellation = scenario.Children.New(AgESTKObjectType.eConstellation, name)
        for stk_object in objects:
            constellation.Objects.AddObject(stk_object)
        print(f"[星座] 成功创建 Constellation: {name}，对象数量={len(objects)}")
        return constellation

    @staticmethod
    def _set_full_ground_track(satellite) -> None:
        ground_track = satellite.Graphics.PassData.GroundTrack
        ground_track.SetLeadDataType(AgELeadTrailData.eDataAll)
        ground_track.SetTrailSameAsLead()
