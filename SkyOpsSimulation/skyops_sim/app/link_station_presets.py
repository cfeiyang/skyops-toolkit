"""建链地点 1 的内置站点和本机保存的站点。"""

from dataclasses import dataclass
from hashlib import sha256

from PySide6.QtCore import QSettings

from skyops_sim.simulations.global_coverage.presets import station_template


@dataclass(frozen=True)
class StationPreset:
    name: str
    latitude_deg: float
    longitude_deg: float


def _built_in_presets() -> tuple[StationPreset, ...]:
    stations = {station.name: station for station in station_template("domestic")}
    return (
        StationPreset("上海临港站", stations["LinGang"].lat, stations["LinGang"].lon),
        StationPreset("喀什站", stations["KaShi"].lat, stations["KaShi"].lon),
    )


def _presets_settings() -> QSettings:
    settings = QSettings("SkyOps", "Simulation")
    settings.beginGroup("linkVisibility/stationPresets")
    return settings


def load_station_presets() -> tuple[StationPreset, ...]:
    built_in = _built_in_presets()
    settings = _presets_settings()
    custom = []
    for key in settings.childKeys():
        record = settings.value(key)
        if not isinstance(record, dict):
            continue
        try:
            name = record["name"].strip()
            lat = float(record["latitude"])
            lon = float(record["longitude"])
        except (AttributeError, KeyError, TypeError, ValueError):
            continue
        if name and -90 <= lat <= 90 and -180 <= lon <= 180:
            custom.append(StationPreset(name, lat, lon))
    return built_in + tuple(sorted(custom, key=lambda station: station.name.casefold()))


def save_station_preset(preset: StationPreset) -> None:
    normalized = preset.name.casefold()
    if not normalized or normalized == "自定义":
        raise ValueError("请先填写具体的站点名称。")
    if not (-90 <= preset.latitude_deg <= 90 and -180 <= preset.longitude_deg <= 180):
        raise ValueError("该站点的经纬度超出范围。")
    # Separate settings keys let different names be saved by separate instances.
    key = sha256(normalized.encode("utf-8")).hexdigest()
    settings = _presets_settings()
    if settings.contains(key) or any(p.name.casefold() == normalized for p in _built_in_presets()):
        raise ValueError("已有同名预设，请换一个站点名称。")
    settings.setValue(key, {
        "name": preset.name,
        "latitude": preset.latitude_deg,
        "longitude": preset.longitude_deg,
    })
    settings.sync()
    if settings.status() != QSettings.Status.NoError:
        raise OSError("无法写入本机的站点预设设置。")
