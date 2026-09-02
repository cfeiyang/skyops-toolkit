from __future__ import annotations

from pathlib import Path

from stk_api.typelib import instance_name, load_stk_modules, qi


class STKObjectsAPI:
    @staticmethod
    def create_facility(scenario, name: str, lat: float, lon: float, alt: float):
        stk_objects, _ = load_stk_modules()
        facility = scenario.Children.New(stk_objects.eFacility, name)
        facility = qi(facility, stk_objects.IAgFacility)
        facility.Position.AssignGeodetic(lat, lon, alt)
        print(f"[地面站] 成功创建 Facility: {name}")
        return facility

    @staticmethod
    def create_satellite_from_tle(root, scenario, name: str, ssc: int, step: float, tle_file: str):
        stk_objects, _ = load_stk_modules()
        tle_path = Path(tle_file)
        if not tle_path.is_file():
            raise FileNotFoundError(f"TLE 文件不存在：{tle_file}")

        satellite = qi(scenario.Children.New(stk_objects.eSatellite, name), stk_objects.IAgSatellite)
        satellite.SetPropagatorType(stk_objects.ePropagatorSGP4)
        propagator = qi(satellite.Propagator, stk_objects.IAgVePropagatorSGP4)
        analysis = root.CurrentScenario.Vgt.EventIntervals.Item("AnalysisInterval")
        propagator.EphemerisInterval.SetImplicitInterval(analysis)
        propagator.Step = step
        propagator.CommonTasks.AddSegsFromFile(str(ssc), str(tle_path))
        propagator.Propagate()
        _set_full_ground_track(satellite, stk_objects)
        print(f"[卫星] 成功创建 {name} (SGP4, SSC={ssc}, Object Model)")
        print("[卫星] 2D Ground Track 已设置为完整 Ephemeris 范围")
        return satellite

    @staticmethod
    def create_satellite_from_elements(root, scenario, sat_cfg: dict):
        stk_objects, _ = load_stk_modules()
        root.UnitPreferences.Item("AngleUnit").SetCurrentUnit("deg")
        root.UnitPreferences.Item("TimeUnit").SetCurrentUnit("sec")
        root.UnitPreferences.Item("DateFormat").SetCurrentUnit("UTCG")

        satellite = qi(
            scenario.Children.New(stk_objects.eSatellite, sat_cfg["name"]),
            stk_objects.IAgSatellite,
        )
        satellite.SetPropagatorType(stk_objects.ePropagatorSGP4)
        propagator = qi(satellite.Propagator, stk_objects.IAgVePropagatorSGP4)
        analysis = root.CurrentScenario.Vgt.EventIntervals.Item("AnalysisInterval")
        propagator.EphemerisInterval.SetImplicitInterval(analysis)
        propagator.Step = sat_cfg["step"]
        propagator.AutoUpdateEnabled = False
        propagator.Segments.SSCNumber = str(sat_cfg["ssc"])
        segment = qi(propagator.Segments.AddSeg(), stk_objects.IAgVeSGP4Segment)
        segment.Epoch = sat_cfg["epoch"]
        segment.MeanMotion = sat_cfg["mean_motion"]
        segment.Eccentricity = sat_cfg["eccentricity"]
        segment.Inclination = sat_cfg["inclination"]
        segment.ArgOfPerigee = sat_cfg["arg_perigee"]
        segment.RAAN = sat_cfg["raan"]
        segment.MeanAnomaly = sat_cfg["mean_anomaly"]
        propagator.Propagate()
        _set_full_ground_track(satellite, stk_objects)
        print(f"[卫星] {sat_cfg['name']} 创建成功")
        return satellite

    @staticmethod
    def create_ground_group(scenario, name: str, facilities: list):
        if not facilities:
            raise ValueError("STKObjects.create_ground_group: facilities 不能为空。")
        if len(facilities) == 1:
            print(f"[地面站] 成功创建 Single station: {instance_name(facilities[0])}")
            return facilities[0]
        return STKObjectsAPI.create_constellation(scenario, name, facilities)

    @staticmethod
    def create_satellite_group(scenario, name: str, satellites: list):
        if not satellites:
            raise ValueError("STKObjects.create_satellite_group: satellites 不能为空。")
        if len(satellites) == 1:
            print(f"[卫星组] Single satellite: {instance_name(satellites[0])}")
            return satellites[0]
        node = STKObjectsAPI.create_constellation(scenario, name, satellites)
        print(f"[卫星组] 成功创建 {len(satellites)} satellites, logic = ANY OF")
        return node

    @staticmethod
    def create_transmitter(parent, name: str):
        stk_objects, _ = load_stk_modules()
        transmitter = qi(parent.Children.New(stk_objects.eTransmitter, name), stk_objects.IAgTransmitter)
        transmitter.SetModel("Simple Transmitter Model")
        return transmitter

    @staticmethod
    def create_receiver(parent, name: str):
        stk_objects, _ = load_stk_modules()
        receiver = qi(parent.Children.New(stk_objects.eReceiver, name), stk_objects.IAgReceiver)
        receiver.SetModel("Simple Receiver Model")
        print(f"[接收机] 成功创建 Receiver: {instance_name(parent)}/{name}")
        return receiver

    @staticmethod
    def load_gps_constellation(root, scenario):
        stk_objects, _ = load_stk_modules()
        print("[GPS] 正在加载 STK 内置 GPS Constellation...")
        root.ExecuteCommand("LoadGPSConstellation *")
        constellations = scenario.Children.GetElements(stk_objects.eConstellation)
        gps = constellations.GetItemByName("GPSConstellation")
        print("[GPS] GPSConstellation 加载完成。")
        return gps

    @staticmethod
    def create_constellation(scenario, name: str, objects: list):
        stk_objects, _ = load_stk_modules()
        if not objects:
            raise ValueError("STKObjects.create_constellation: objects 不能为空。")
        constellation = qi(scenario.Children.New(stk_objects.eConstellation, name), stk_objects.IAgConstellation)
        for obj in objects:
            constellation.Objects.AddObject(obj)
        print(f"[星座] 成功创建 Constellation: {name}，对象数量={len(objects)}")
        return constellation

    @staticmethod
    def get_gps_satellites(scenario) -> list:
        stk_objects, _ = load_stk_modules()
        satellites = scenario.Children.GetElements(stk_objects.eSatellite)
        gps = []
        for i in range(satellites.Count):
            sat = satellites.Item(i)
            sat_name = instance_name(sat).lower()
            if sat_name.startswith("gps-"):
                gps.append(qi(sat, stk_objects.IAgSatellite))
        print(f"[GPS] 找到 GPS Satellite 数量：{len(gps)}")
        return gps


def _set_full_ground_track(satellite, stk_objects):
    try:
        graphics = qi(satellite.Graphics, stk_objects.IAgSaGraphics)
        ground_track = graphics.PassData.GroundTrack
        ground_track.SetLeadDataType(stk_objects.eDataAll)
        ground_track.SetTrailSameAsLead()
    except Exception as exc:
        print(f"[卫星] 设置 Ground Track 跳过：{exc}")
