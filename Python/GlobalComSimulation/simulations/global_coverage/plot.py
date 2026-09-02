from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from scipy.interpolate import LinearNDInterpolator

from stk_api.typelib import com_float_array
from utils.geo import behrmann_fwd, load_coastline, wrap_lon


def configure_chinese_font():
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False


def save_axes_image(ax, image_path, dpi: int = 300):
    ax.figure.savefig(image_path, dpi=dpi, bbox_inches="tight", facecolor="white")


def nice_level_step(max_hour: float) -> tuple[float, float]:
    if not np.isfinite(max_hour) or max_hour <= 0:
        return 1.0, 1.0
    raw_step = max_hour / 8.0
    base = 10 ** np.floor(np.log10(raw_step))
    ratio = raw_step / base
    if ratio <= 1:
        nice = 1
    elif ratio <= 2:
        nice = 2
    elif ratio <= 5:
        nice = 5
    else:
        nice = 10
    level_step = nice * base
    max_level = np.ceil(max_hour / level_step) * level_step
    return float(level_step), float(max_level)


def plot_global_coverage(result, cfg, ax=None):
    configure_chinese_font()
    p = cfg.plot
    cov = result.coverage_data
    lat = cov["LatitudeDeg"].to_numpy()
    lon = cov["LongitudeDeg"].to_numpy()
    time_hour = cov["TimeHour"].to_numpy()

    max_hour = float(np.nanmax(time_hour)) if len(time_hour) else 0.0
    level_step, max_level = nice_level_step(max_hour)
    levels = np.arange(0, max_level + 0.5 * level_step, level_step)

    lon = np.mod(lon, 360.0)
    lon_ext = np.concatenate([lon - 360.0, lon, lon + 360.0])
    lat_ext = np.concatenate([lat, lat, lat])
    time_ext = np.concatenate([time_hour, time_hour, time_hour])

    lon_grid, lat_grid = np.meshgrid(
        np.arange(p.lon_range[0], p.lon_range[1] + p.interp_step, p.interp_step),
        np.arange(p.lat_range[0], p.lat_range[1] + p.interp_step, p.interp_step),
    )
    interpolant = LinearNDInterpolator(np.column_stack([lon_ext, lat_ext]), time_ext)
    time_grid = interpolant(lon_grid, lat_grid)
    time_grid = np.where(time_grid <= 0, np.nan, time_grid)

    sat_tracks = [
        _read_satellite_track(sat, result.scenario, p) for sat in result.satellites
    ]

    x_grid, y_grid = behrmann_fwd(lat_grid, lon_grid, p.center_lon)
    x_sats, y_sats = [], []
    for sat_lat, sat_lon in sat_tracks:
        x, y = behrmann_fwd(sat_lat, sat_lon, p.center_lon)
        x_sats.append(x)
        y_sats.append(y)

    coast_lat, coast_lon = load_coastline(cfg.paths.data_dir)
    coast_lon = wrap_lon(coast_lon, p.lon_range[0])
    jump = np.concatenate([[False], np.abs(np.diff(coast_lon)) > 180])
    coast_lat = coast_lat.astype(float).copy()
    coast_lon = coast_lon.astype(float).copy()
    coast_lat[jump] = np.nan
    coast_lon[jump] = np.nan
    x_coast, y_coast = behrmann_fwd(coast_lat, coast_lon, p.center_lon)

    stations = [s for s in result.cfg.stations if s.get("enabled", True)]
    st_lat = np.array([s["lat"] for s in stations], dtype=float)
    st_lon = np.array([s["lon"] for s in stations], dtype=float)
    x_st, y_st = behrmann_fwd(st_lat, st_lon, p.center_lon)

    standalone = ax is None
    if standalone:
        fig, ax = plt.subplots(figsize=(14, 6.5), facecolor="white")
    else:
        ax.clear()

    contour = ax.contourf(
        x_grid,
        y_grid,
        time_grid,
        levels=levels,
        cmap="viridis",
        extend="max",
    )

    if p.show_contour_labels and len(levels) > 1:
        line_contour = ax.contour(
            x_grid, y_grid, time_grid, levels=levels[1:], colors="k", linewidths=0.4
        )
        ax.clabel(line_contour, fmt="%.2g", fontsize=9)

    ax.plot(x_coast, y_coast, color="k", linewidth=1)
    colors = plt.cm.tab10(np.linspace(0, 1, max(len(x_sats), 1)))
    for i, (xs, ys) in enumerate(zip(x_sats, y_sats)):
        ax.plot(xs, ys, color=colors[i], linewidth=1.3)
    for i, station in enumerate(stations):
        ax.plot(
            x_st[i],
            y_st[i],
            "o",
            markersize=8,
            markerfacecolor=colors[i % len(colors)],
            markeredgecolor="k",
        )
        ax.text(x_st[i], y_st[i], " " + station["name"], fontsize=10, fontweight="bold", va="center")

    x_ticks, _ = behrmann_fwd(np.zeros(len(p.lon_ticks)), np.array(p.lon_ticks), p.center_lon)
    _, y_ticks = behrmann_fwd(np.array(p.lat_ticks), np.full(len(p.lat_ticks), p.center_lon), p.center_lon)
    ax.set_xticks(x_ticks)
    ax.set_xticklabels(p.lon_tick_labels)
    ax.set_yticks(y_ticks)
    ax.set_yticklabels(p.lat_tick_labels)

    x_lim, _ = behrmann_fwd(np.array([0.0, 0.0]), np.array(p.lon_range), p.center_lon)
    _, y_lim = behrmann_fwd(np.array(p.lat_range), np.array([p.center_lon, p.center_lon]), p.center_lon)
    ax.set_xlim(sorted(x_lim))
    ax.set_ylim(sorted(y_lim))
    ax.set_aspect("equal")
    ax.grid(True, linestyle=":", alpha=0.25)
    ax.set_xlabel("经度/°")
    ax.set_ylabel("纬度/°")
    colorbar = ax.figure.colorbar(contour, ax=ax, fraction=0.03, pad=0.02)
    colorbar.set_label("通信时长 / h")
    colorbar.set_ticks(levels)
    if getattr(p, "title", ""):
        ax.set_title(p.title)
    print(f"[绘图] 全球通信时长图完成，max = {max_hour:.3f} h, step = {level_step:.3f} h")
    if standalone:
        ax.figure.tight_layout()
    return ax


def _read_satellite_track(satellite, scenario, plot_cfg):
    lla = satellite.DataProviders.Item("LLA State").Group.Item("Fixed")
    data = lla.Exec(scenario.StartTime, scenario.StopTime, plot_cfg.track_step)
    lat = com_float_array(data.DataSets.GetDataSetByName("Lat").GetValues())
    lon = com_float_array(data.DataSets.GetDataSetByName("Lon").GetValues())
    lon = wrap_lon(lon, plot_cfg.lon_range[0])
    jump = np.concatenate([[False], np.abs(np.diff(lon)) > 180])
    lat = lat.copy()
    lon = lon.copy()
    lat[jump] = np.nan
    lon[jump] = np.nan
    return lat, lon
