"""基于 Skyfield 的卫星可见性计算，替代原 STK Access 分析。

纯计算模块，不依赖 Streamlit，可独立测试：
- SGP4 推算卫星位置（两行根数），WGS84 站点坐标；
- 可见条件 = 仰角 >= 最低仰角；
- 粗网格扫描 + 二分法把窗口边界精化到秒级；
- 输出可见窗口与 AER 采样序列。

时间约定：入口参数为北京时间（Asia/Shanghai），内部转 UTC 计算，输出本地时间字符串。
仰角为几何值（不修正大气折射），与 STK 仰角约束口径一致。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

from skyfield.api import EarthSatellite, Loader, wgs84

import numpy as np

from app.paths import DATA_DIR

LOCAL_TZ = ZoneInfo("Asia/Shanghai")
_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
_MAX_SPAN_DAYS = 8.0

# GSO（静止轨道）干扰规避默认值：
# 隔离角阈值 15°：等价于 STK Access 约束「Special → Geostationary Belt Exclusion」，
# 约束视线方向与静止轨道带的角距，低于该值即不可用（与本项目 STK 仿真取值一致）。
_DEFAULT_GSO_AVOID_DEG = 15.0

_GEO_RADIUS_KM = 42164.0
_EARTH_RADIUS_KM = 6371.0


@dataclass(frozen=True)
class StationConfig:
    name: str
    latitude_deg: float
    longitude_deg: float
    altitude_m: float
    min_elevation_deg: float
    mask: Tuple[Tuple[float, float, float], ...] = ()
    gso_avoid_deg: float = _DEFAULT_GSO_AVOID_DEG


@dataclass(frozen=True)
class AccessInterval:
    access_number: int
    start_time: str
    stop_time: str
    duration_sec: float
    max_elevation_deg: float
    max_elevations: Tuple[Tuple[str, float], ...]
    clipped_start: bool
    clipped_stop: bool
    max_elevation_time: str = ""
    max_elevation_times: Tuple[Tuple[str, str], ...] = ()


@dataclass(frozen=True)
class AERSample:
    access_number: int
    station_name: str
    time: str
    azimuth_deg: float
    elevation_deg: float
    range_km: float


@dataclass(frozen=True)
class VisibilityResult:
    satellite_name: str
    tle_line1: str
    tle_line2: str
    start_time: str
    stop_time: str
    station_names: Tuple[str, ...]
    access_intervals: Tuple[AccessInterval, ...]
    aer_samples: Tuple[AERSample, ...]

    @property
    def total_visible_sec(self) -> float:
        return sum(item.duration_sec for item in self.access_intervals)


def _gso_arc(station: StationConfig, step_deg: float = 2.0) -> np.ndarray:
    """观测站可见的静止轨道弧采样，返回 N×2 的 (方位角°, 仰角°) 数组。

    对静止轨道所有经度采样，只保留地平线以上（仰角 > 0）的部分——
    地平线以下的静止卫星被地球遮挡，不构成干扰。
    """
    lat = np.radians(station.latitude_deg)
    lon = np.radians(station.longitude_deg)
    sx = _EARTH_RADIUS_KM * np.cos(lat) * np.cos(lon)
    sy = _EARTH_RADIUS_KM * np.cos(lat) * np.sin(lon)
    sz = _EARTH_RADIUS_KM * np.sin(lat)
    east = np.array([-np.sin(lon), np.cos(lon), 0.0])
    north = np.array([-np.sin(lat) * np.cos(lon), -np.sin(lat) * np.sin(lon), np.cos(lat)])
    up = np.array([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)])

    rows = []
    for g_lon in np.arange(-180.0, 180.0, step_deg):
        gl = np.radians(float(g_lon))
        d = np.array([_GEO_RADIUS_KM * np.cos(gl) - sx,
                      _GEO_RADIUS_KM * np.sin(gl) - sy,
                      -sz])
        dist = float(np.linalg.norm(d))
        if dist <= 0.0:
            continue
        el = float(np.degrees(np.arcsin(np.clip(float(d @ up) / dist, -1.0, 1.0))))
        if el <= 0.0:
            continue
        az = float(np.degrees(np.arctan2(float(d @ east), float(d @ north))) % 360.0)
        rows.append((az, el))
    return np.array(rows, dtype=float) if rows else np.zeros((0, 2), dtype=float)


def _gso_separation_deg(azimuth_deg, elevation_deg, arc) -> np.ndarray:
    """卫星方向与静止轨道弧的最小角距（度）。arc 为空时返回 90°（视为无约束）。"""
    az = np.radians(np.asarray(azimuth_deg, dtype=float))
    el = np.radians(np.asarray(elevation_deg, dtype=float))
    if arc is None or len(arc) == 0:
        return np.full(np.shape(az), 90.0)
    arc_az = np.radians(arc[:, 0])
    arc_el = np.radians(arc[:, 1])
    cos_sep = (np.sin(el)[..., None] * np.sin(arc_el)[None, ...]
               + np.cos(el)[..., None] * np.cos(arc_el)[None, ...]
               * np.cos(az[..., None] - arc_az[None, ...]))
    result = np.degrees(np.arccos(np.clip(cos_sep, -1.0, 1.0))).min(axis=-1)
    # 标量输入时 squeeze 成 0 维，避免 float() 报「仅 0 维数组可转换」
    return np.squeeze(result)


class _StationSpec:
    """单站的预绑定计算句柄：站点坐标与可见条件。"""

    def __init__(self, timescale, satellite, station: StationConfig) -> None:
        self.station = station
        self.timescale = timescale
        self.satellite = satellite
        self.geocentric = wgs84.latlon(
            station.latitude_deg, station.longitude_deg, elevation_m=station.altitude_m
        )
        self.topocentric = satellite - self.geocentric
        # 每站只预计算一次 GSO 弧，供干扰规避判据使用
        self.gso_arc = _gso_arc(station) if station.gso_avoid_deg > 0 else np.zeros((0, 2))

    def altaz(self, t):
        return self.topocentric.at(t).altaz()

    def visible_at(self, t) -> "object":
        altitude, azimuth, _ = self.altaz(t)
        minimum = _mask_elevation(
            azimuth.degrees, self.station.min_elevation_deg, self.station.mask
        )
        ok = altitude.degrees >= minimum
        if self.station.gso_avoid_deg > 0 and len(self.gso_arc):
            separation = _gso_separation_deg(azimuth.degrees, altitude.degrees, self.gso_arc)
            ok = ok & (separation >= self.station.gso_avoid_deg)
        return ok

    def elevation_deg(self, t) -> float:
        return float(self.altaz(t)[0].degrees)


def _mask_elevation(
    azimuth_deg,
    base_min_elevation: float,
    mask: Sequence[Tuple[float, float, float]],
):
    """按方位角计算有效最低仰角：基础掩角与各遮挡段掩角取最大值。

    mask 每项为 (起始方位角°, 结束方位角°, 掩角°)，方位角区间可跨 360°。
    返回与 azimuth_deg 同形的数值（标量输入返回标量级，数组输入返回数组）。
    """
    azimuth = np.asarray(azimuth_deg, dtype=float)
    effective = np.full(np.shape(azimuth), float(base_min_elevation), dtype=float)
    for start, end, elevation in mask:
        start = float(start) % 360.0
        end = float(end) % 360.0
        if abs(start - end) < 1e-9:
            continue
        if start < end:
            inside = (azimuth >= start) & (azimuth < end)
        else:  # 跨 0°/360° 的区间
            inside = (azimuth >= start) | (azimuth < end)
        effective = np.maximum(effective, np.where(inside, float(elevation), -1e9))
    return effective


def compute_visibility(
    line1: str,
    line2: str,
    satellite_name: str,
    stations: Sequence[StationConfig],
    start_local: datetime,
    stop_local: datetime,
    coarse_step_sec: float = 60.0,
    refine_step_sec: float = 1.0,
    sample_step_sec: float = 60.0,
    sample_stations: Optional[Sequence[StationConfig]] = None,
) -> VisibilityResult:
    """计算可见窗口。

    stations 决定窗口判定（双站即取交集）；sample_stations 决定 AER 采样与
    最高仰角统计，缺省与 stations 相同。
    """
    if not stations:
        raise ValueError("至少需要一个地面站。")
    names = [station.name for station in stations]
    if len(set(names)) != len(names):
        raise ValueError("地面站名称不能重复。")
    for station in list(stations) + (list(sample_stations) if sample_stations else []):
        if not -90.0 <= station.latitude_deg <= 90.0:
            raise ValueError("纬度必须在 -90°～90° 之间。")
        if not -180.0 <= station.longitude_deg <= 180.0:
            raise ValueError("经度必须在 -180°～180° 之间。")
    start = _as_local(start_local)
    stop = _as_local(stop_local)
    if stop <= start:
        raise ValueError("结束时间必须晚于开始时间。")
    span_sec = (stop - start).total_seconds()
    if span_sec > _MAX_SPAN_DAYS * 86400:
        raise ValueError(f"单次计算最长 {_MAX_SPAN_DAYS:g} 天，请分段计算。")
    for step in (coarse_step_sec, refine_step_sec, sample_step_sec):
        if step <= 0:
            raise ValueError("采样步长必须为正数秒。")

    display = list(sample_stations) if sample_stations else list(stations)
    if not display:
        raise ValueError("采样站点不能为空。")

    loader = Loader(str(DATA_DIR))
    timescale = loader.timescale(builtin=True)
    satellite = EarthSatellite(line1, line2, satellite_name, timescale)
    specs = [_StationSpec(timescale, satellite, station) for station in stations]
    display_specs = [_StationSpec(timescale, satellite, station) for station in display]

    start_utc = start.astimezone(timezone.utc)
    stop_utc = stop.astimezone(timezone.utc)
    grid = _build_grid(start_utc, stop_utc, coarse_step_sec)
    t_grid = timescale.from_datetimes(grid)

    combined = specs[0].visible_at(t_grid)
    for spec in specs[1:]:
        combined = combined & spec.visible_at(t_grid)
    runs = _true_runs(combined)

    intervals: List[AccessInterval] = []
    samples: List[AERSample] = []
    for number, (i0, i1) in enumerate(runs, start=1):
        clipped_start = i0 == 0
        clipped_stop = i1 == len(grid) - 1
        window_start = grid[i0]
        window_stop = grid[i1]
        if not clipped_start:
            window_start = _refine_rise(specs, timescale, grid[i0 - 1], grid[i0], refine_step_sec)
        if not clipped_stop:
            window_stop = _refine_set(specs, timescale, grid[i1], grid[i1 + 1], refine_step_sec)

        elev_pairs = []
        time_pairs = []
        for spec in display_specs:
            value, peak_utc = _max_elevation(spec, window_start, window_stop)
            elev_pairs.append((spec.station.name, value))
            time_pairs.append((spec.station.name, _fmt_local(peak_utc)))
        best = max(range(len(elev_pairs)), key=lambda idx: elev_pairs[idx][1])
        intervals.append(
            AccessInterval(
                access_number=number,
                start_time=_fmt_local(window_start),
                stop_time=_fmt_local(window_stop),
                duration_sec=(window_stop - window_start).total_seconds(),
                max_elevation_deg=elev_pairs[best][1],
                max_elevations=tuple(elev_pairs),
                clipped_start=clipped_start,
                clipped_stop=clipped_stop,
                max_elevation_time=time_pairs[best][1],
                max_elevation_times=tuple(time_pairs),
            )
        )
        samples.extend(_window_samples(display_specs, timescale, number, window_start, window_stop, sample_step_sec))

    return VisibilityResult(
        satellite_name=satellite_name,
        tle_line1=line1,
        tle_line2=line2,
        start_time=_fmt_local(start_utc),
        stop_time=_fmt_local(stop_utc),
        station_names=tuple(spec.station.name for spec in display_specs),
        access_intervals=tuple(intervals),
        aer_samples=tuple(samples),
    )


@dataclass(frozen=True)
class AERPoint:
    time: str
    azimuth_deg: float
    elevation_deg: float
    range_km: float


@dataclass(frozen=True)
class FullAERResult:
    satellite_name: str
    tle_line1: str
    tle_line2: str
    start_time: str
    stop_time: str
    station_name: str
    samples: Tuple[AERPoint, ...]


def compute_full_aer(
    line1: str,
    line2: str,
    satellite_name: str,
    station: StationConfig,
    start_local: datetime,
    stop_local: datetime,
    step_sec: float = 60.0,
) -> FullAERResult:
    """全时段 AER 序列：仰角可为负（卫星在地平线以下），无任何可见性约束。

    供任务二绘制仰角/方位角/距离曲线；只画可见段时由调用方用
    filter_visible 过滤（几何仰角 >= 0，对应 STK 仅保留视线约束）。
    """
    start = _as_local(start_local)
    stop = _as_local(stop_local)
    if stop <= start:
        raise ValueError("结束时间必须晚于开始时间。")
    if (stop - start).total_seconds() > _MAX_SPAN_DAYS * 86400:
        raise ValueError(f"单次计算最长 {_MAX_SPAN_DAYS:g} 天，请分段计算。")
    if step_sec <= 0:
        raise ValueError("采样步长必须为正数秒。")
    if not -90.0 <= station.latitude_deg <= 90.0:
        raise ValueError("纬度必须在 -90°～90° 之间。")
    if not -180.0 <= station.longitude_deg <= 180.0:
        raise ValueError("经度必须在 -180°～180° 之间。")

    loader = Loader(str(DATA_DIR))
    timescale = loader.timescale(builtin=True)
    satellite = EarthSatellite(line1, line2, satellite_name, timescale)
    spec = _StationSpec(timescale, satellite, station)

    start_utc = start.astimezone(timezone.utc)
    stop_utc = stop.astimezone(timezone.utc)
    grid = _build_grid(start_utc, stop_utc, step_sec)
    t = timescale.from_datetimes(grid)
    altitude, azimuth, distance = spec.altaz(t)
    samples = tuple(
        AERPoint(
            time=_fmt_local(dt),
            azimuth_deg=float(azimuth.degrees[idx]),
            elevation_deg=float(altitude.degrees[idx]),
            range_km=float(distance.km[idx]),
        )
        for idx, dt in enumerate(grid)
    )
    return FullAERResult(
        satellite_name=satellite_name,
        tle_line1=line1,
        tle_line2=line2,
        start_time=_fmt_local(start_utc),
        stop_time=_fmt_local(stop_utc),
        station_name=station.name,
        samples=samples,
    )


def filter_visible(samples: Sequence[AERPoint]) -> Tuple[AERPoint, ...]:
    """视线可见段：几何仰角 >= 0（不修正折射），对应 STK 仅保留视线约束的 Access。"""
    return tuple(point for point in samples if point.elevation_deg >= 0.0)


def _build_grid(start_utc: datetime, stop_utc: datetime, step_sec: float) -> List[datetime]:
    span = (stop_utc - start_utc).total_seconds()
    count = int(span // step_sec) + 1
    grid = [start_utc + timedelta(seconds=i * step_sec) for i in range(count)]
    if (stop_utc - grid[-1]).total_seconds() > 1e-6:
        grid.append(stop_utc)
    return grid


def _true_runs(mask) -> List[Tuple[int, int]]:
    runs: List[Tuple[int, int]] = []
    i, n = 0, len(mask)
    while i < n:
        if mask[i]:
            j = i
            while j + 1 < n and mask[j + 1]:
                j += 1
            runs.append((i, j))
            i = j + 1
        else:
            i += 1
    return runs


def _all_visible(specs: Sequence[_StationSpec], timescale, dt_utc: datetime) -> bool:
    t = timescale.from_datetime(dt_utc)
    return all(bool(spec.visible_at(t)) for spec in specs)


def _refine_rise(specs, timescale, invisible: datetime, visible: datetime, step_sec: float) -> datetime:
    while (visible - invisible).total_seconds() > step_sec:
        mid = invisible + (visible - invisible) / 2
        if _all_visible(specs, timescale, mid):
            visible = mid
        else:
            invisible = mid
    return visible


def _refine_set(specs, timescale, visible: datetime, invisible: datetime, step_sec: float) -> datetime:
    while (invisible - visible).total_seconds() > step_sec:
        mid = visible + (invisible - visible) / 2
        if _all_visible(specs, timescale, mid):
            visible = mid
        else:
            invisible = mid
    return visible


def _max_elevation(
    spec: _StationSpec, start_utc: datetime, stop_utc: datetime, iterations: int = 36
) -> Tuple[float, datetime]:
    """三元搜索窗口内最高仰角，返回（仰角值, 对应 UTC 时刻）。"""
    lo, hi = start_utc, stop_utc
    for _ in range(iterations):
        m1 = lo + (hi - lo) / 3
        m2 = hi - (hi - lo) / 3
        if _elevation_at(spec, m1) < _elevation_at(spec, m2):
            lo = m1
        else:
            hi = m2
    candidates = (lo, lo + (hi - lo) / 2, hi)
    values = [_elevation_at(spec, moment) for moment in candidates]
    best = max(range(3), key=lambda idx: values[idx])
    return values[best], candidates[best]


def _elevation_at(spec: _StationSpec, dt_utc: datetime) -> float:
    return spec.elevation_deg(spec.timescale.from_datetime(dt_utc))


def _window_samples(
    specs: Sequence[_StationSpec],
    timescale,
    access_number: int,
    start_utc: datetime,
    stop_utc: datetime,
    step_sec: float,
) -> List[AERSample]:
    span = (stop_utc - start_utc).total_seconds()
    count = int(span // step_sec) + 1
    times = [start_utc + timedelta(seconds=i * step_sec) for i in range(count)]
    if (stop_utc - times[-1]).total_seconds() > 1e-6:
        times.append(stop_utc)
    t = timescale.from_datetimes(times)
    rows: List[AERSample] = []
    for spec in specs:
        altitude, azimuth, distance = spec.altaz(t)
        for idx, dt in enumerate(times):
            rows.append(
                AERSample(
                    access_number=access_number,
                    station_name=spec.station.name,
                    time=_fmt_local(dt),
                    azimuth_deg=float(azimuth.degrees[idx]),
                    elevation_deg=float(altitude.degrees[idx]),
                    range_km=float(distance.km[idx]),
                )
            )
    return rows


def _as_local(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=LOCAL_TZ)
    return value.astimezone(LOCAL_TZ)


def _fmt_local(value: datetime) -> str:
    return value.astimezone(LOCAL_TZ).strftime(_TIME_FORMAT)


@dataclass(frozen=True)
class GroundTrackPoint:
    time: str
    latitude_deg: float
    longitude_deg: float
    elevation_deg: float = 0.0
    linked: bool = False
    elev_ok: bool = False        # 满足最低仰角 / 掩角约束
    gso_sep_deg: float = 90.0    # 与静止轨道弧的角距
    block_reason: str = ""       # '' | 'mask' | 'gso'


def compute_ground_track(
    line1: str,
    line2: str,
    satellite_name: str,
    start_local: datetime,
    stop_local: datetime,
    step_sec: float = 60.0,
    station: Optional[StationConfig] = None,
) -> Tuple[GroundTrackPoint, ...]:
    """卫星星下点轨迹采样，供前端地图绘制地面轨迹与建链线。

    传入 station 时同时计算该站的仰角与建链状态（含掩角/干扰约束）。
    """
    start = _as_local(start_local)
    stop = _as_local(stop_local)
    if stop <= start:
        raise ValueError("结束时间必须晚于开始时间。")
    if (stop - start).total_seconds() > _MAX_SPAN_DAYS * 86400:
        raise ValueError(f"单次计算最长 {_MAX_SPAN_DAYS:g} 天，请分段计算。")
    if step_sec <= 0:
        raise ValueError("采样步长必须为正数秒。")

    loader = Loader(str(DATA_DIR))
    timescale = loader.timescale(builtin=True)
    satellite = EarthSatellite(line1, line2, satellite_name, timescale)

    start_utc = start.astimezone(timezone.utc)
    stop_utc = stop.astimezone(timezone.utc)
    grid = _build_grid(start_utc, stop_utc, step_sec)
    t = timescale.from_datetimes(grid)
    subpoint = satellite.at(t).subpoint()
    latitudes = subpoint.latitude.degrees
    longitudes = subpoint.longitude.degrees

    elevations = None
    elev_ok = None
    gso_sep = None
    gso_blocked = None
    linked = None
    if station is not None:
        spec = _StationSpec(timescale, satellite, station)
        altitude, azimuth, _ = spec.altaz(t)
        elevations = np.asarray(altitude.degrees)
        minimum = _mask_elevation(azimuth.degrees, station.min_elevation_deg, station.mask)
        elev_ok = np.asarray(elevations >= minimum)
        # GSO 弧隔离角判据
        if station.gso_avoid_deg > 0 and len(spec.gso_arc):
            gso_sep = np.asarray(
                _gso_separation_deg(azimuth.degrees, elevations, spec.gso_arc)
            )
            gso_blocked = gso_sep < station.gso_avoid_deg
        else:
            gso_sep = np.full(np.shape(elevations), 90.0)
            gso_blocked = np.zeros(np.shape(elevations), dtype=bool)
        linked = elev_ok & ~gso_blocked

    def _reason(idx: int) -> str:
        if elev_ok is None:
            return ""
        if not bool(elev_ok[idx]):
            return "mask"
        if bool(gso_blocked[idx]):
            return "gso"
        return ""

    return tuple(
        GroundTrackPoint(
            time=_fmt_local(dt),
            latitude_deg=float(latitudes[idx]),
            longitude_deg=float(longitudes[idx]),
            elevation_deg=float(elevations[idx]) if elevations is not None else 0.0,
            linked=bool(linked[idx]) if linked is not None else False,
            elev_ok=bool(elev_ok[idx]) if elev_ok is not None else False,
            gso_sep_deg=float(gso_sep[idx]) if gso_sep is not None else 90.0,
            block_reason=_reason(idx),
        )
        for idx, dt in enumerate(grid)
    )


@dataclass(frozen=True)
class SubPoint:
    time: str
    latitude_deg: float
    longitude_deg: float
    altitude_km: float
    elevation_deg: Optional[float] = None
    linked: Optional[bool] = None
    gso_sep_deg: Optional[float] = None
    block_reason: str = ""


def compute_subpoint(
    line1: str,
    line2: str,
    satellite_name: str,
    moment: datetime,
    station: Optional[StationConfig] = None,
) -> SubPoint:
    """单点星下点（实时位置）：返回经纬度、高度，以及（可选）对某站的仰角与建链状态。"""
    local = _as_local(moment)
    loader = Loader(str(DATA_DIR))
    timescale = loader.timescale(builtin=True)
    satellite = EarthSatellite(line1, line2, satellite_name, timescale)
    t = timescale.from_datetime(local)
    geo = satellite.at(t).subpoint()
    try:
        altitude_km = float(geo.elevation.km)
    except AttributeError:
        altitude_km = 0.0

    elevation_deg = None
    linked = None
    gso_sep_deg = None
    reason = ""
    if station is not None:
        spec = _StationSpec(timescale, satellite, station)
        altitude, azimuth, _ = spec.altaz(t)
        elevation_deg = float(altitude.degrees)
        minimum = float(
            _mask_elevation(azimuth.degrees, station.min_elevation_deg, station.mask)
        )
        elev_ok = elevation_deg >= minimum
        if station.gso_avoid_deg > 0 and len(spec.gso_arc):
            gso_sep_deg = float(
                _gso_separation_deg(azimuth.degrees, altitude.degrees, spec.gso_arc)
            )
            gso_ok = gso_sep_deg >= station.gso_avoid_deg
        else:
            gso_sep_deg = 90.0
            gso_ok = True
        linked = bool(elev_ok and gso_ok)
        if not elev_ok:
            reason = "mask"
        elif not gso_ok:
            reason = "gso"

    return SubPoint(
        time=_fmt_local(local),
        latitude_deg=float(geo.latitude.degrees),
        longitude_deg=float(geo.longitude.degrees),
        altitude_km=altitude_km,
        elevation_deg=elevation_deg,
        linked=linked,
        gso_sep_deg=gso_sep_deg,
        block_reason=reason,
    )
