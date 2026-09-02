"""全球通信时长梯度图，对应 MATLAB/plotGlobalCoverage.m。"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.basemap import Basemap
from scipy.interpolate import LinearNDInterpolator

from stk_api.data import numeric_dataset


def configure_chinese_font() -> None:
    plt.rcParams["font.sans-serif"] = [
        "Microsoft YaHei",
        "SimHei",
        "DejaVu Sans",
    ]
    plt.rcParams["axes.unicode_minus"] = False


def save_axes_image(axes, image_path: str | Path, dpi: int = 300) -> None:
    axes.figure.savefig(
        image_path, dpi=dpi, bbox_inches="tight", facecolor="white"
    )


def plot_global_coverage(result, config, axes=None):
    configure_chinese_font()
    plot_config = config.plot
    coverage_data = result.coverage_data

    latitude = coverage_data["LatitudeDeg"].to_numpy(dtype=float)
    longitude = coverage_data["LongitudeDeg"].to_numpy(dtype=float)
    time_hours = coverage_data["TimeHour"].to_numpy(dtype=float)

    max_hour = (
        float(np.nanmax(time_hours))
        if time_hours.size and np.any(np.isfinite(time_hours))
        else float("nan")
    )
    level_step, max_level = _nice_level_step(max_hour)
    levels = np.arange(0.0, max_level + level_step * 0.5, level_step)

    longitude = np.mod(longitude, 360.0)
    extended_longitude = np.concatenate(
        [longitude - 360.0, longitude, longitude + 360.0]
    )
    extended_latitude = np.concatenate([latitude, latitude, latitude])
    extended_time = np.concatenate([time_hours, time_hours, time_hours])

    longitude_grid, latitude_grid = np.meshgrid(
        np.arange(
            plot_config.lon_range[0],
            plot_config.lon_range[1] + plot_config.interp_step * 0.5,
            plot_config.interp_step,
        ),
        np.arange(
            plot_config.lat_range[0],
            plot_config.lat_range[1] + plot_config.interp_step * 0.5,
            plot_config.interp_step,
        ),
    )
    interpolator = LinearNDInterpolator(
        np.column_stack([extended_longitude, extended_latitude]),
        extended_time,
        fill_value=np.nan,
    )
    time_grid = interpolator(longitude_grid, latitude_grid)
    time_grid[time_grid <= 0] = np.nan

    satellite_tracks = [
        _read_satellite_track(satellite, result.scenario, plot_config)
        for satellite in result.satellites
    ]

    standalone = axes is None
    if standalone:
        _, axes = plt.subplots(figsize=(14, 6.5), facecolor="white")
    else:
        _remove_existing_colorbar(axes)
        axes.clear()

    world_map = Basemap(
        projection="cea",
        lat_ts=30,
        lon_0=plot_config.center_lon,
        llcrnrlon=plot_config.lon_range[0],
        urcrnrlon=plot_config.lon_range[1],
        llcrnrlat=plot_config.lat_range[0],
        urcrnrlat=plot_config.lat_range[1],
        resolution="c",
        ax=axes,
    )

    x_grid, y_grid = world_map(longitude_grid, latitude_grid)
    filled_contour = world_map.contourf(
        x_grid,
        y_grid,
        time_grid,
        levels=levels,
        cmap="viridis",
        ax=axes,
    )

    if plot_config.show_contour_labels and levels.size > 1:
        contour_lines = world_map.contour(
            x_grid,
            y_grid,
            time_grid,
            levels=levels[1:],
            colors="k",
            linewidths=0.5,
            ax=axes,
        )
        axes.clabel(
            contour_lines,
            levels=levels[1:],
            inline=True,
            fontsize=9,
            fmt="%.2g",
        )

    world_map.drawcoastlines(color="k", linewidth=1.0, ax=axes)

    track_colors = plt.cm.tab10(
        np.linspace(0.0, 1.0, max(len(satellite_tracks), 1))
    )
    for index, (track_latitude, track_longitude) in enumerate(satellite_tracks):
        track_x, track_y = world_map(track_longitude, track_latitude)
        axes.plot(
            track_x,
            track_y,
            color=track_colors[index],
            linewidth=1.3,
        )

    enabled_stations = [station for station in result.cfg.stations if station.enabled]
    station_colors = plt.cm.tab10(
        np.linspace(0.0, 1.0, max(len(enabled_stations), 1))
    )
    for index, station in enumerate(enabled_stations):
        station_x, station_y = world_map(station.lon, station.lat)
        axes.plot(
            station_x,
            station_y,
            marker="o",
            linestyle="none",
            markersize=8,
            markerfacecolor=station_colors[index],
            markeredgecolor="k",
            markeredgewidth=1,
        )
        axes.text(
            station_x,
            station_y,
            f" {station.name}",
            fontsize=10,
            fontweight="bold",
            color="k",
            horizontalalignment="left",
            verticalalignment="center",
        )

    tick_x, _ = world_map(
        np.asarray(plot_config.lon_ticks, dtype=float),
        np.zeros(len(plot_config.lon_ticks)),
    )
    _, tick_y = world_map(
        np.full(len(plot_config.lat_ticks), plot_config.center_lon),
        np.asarray(plot_config.lat_ticks, dtype=float),
    )
    axes.set_xticks(tick_x)
    axes.set_xticklabels(plot_config.lon_tick_labels)
    axes.set_yticks(tick_y)
    axes.set_yticklabels(plot_config.lat_tick_labels)
    axes.set_xlim(world_map.xmin, world_map.xmax)
    axes.set_ylim(world_map.ymin, world_map.ymax)
    axes.set_aspect("equal", adjustable="box")
    axes.grid(True, linestyle=":", alpha=0.25)
    axes.set_xlabel("经度/°")
    axes.set_ylabel("纬度/°")

    colorbar = axes.figure.colorbar(
        filled_contour, ax=axes, orientation="vertical", fraction=0.03, pad=0.02
    )
    colorbar.set_ticks(levels)
    colorbar.set_label("通信时长 / h")
    axes._stk_colorbar = colorbar  # type: ignore[attr-defined]

    if plot_config.title:
        axes.set_title(plot_config.title, fontweight="normal")

    def format_coordinates(x_value: float, y_value: float) -> str:
        lon_value, lat_value = world_map(x_value, y_value, inverse=True)
        lookup_lon = (
            (lon_value - plot_config.lon_range[0]) % 360.0
            + plot_config.lon_range[0]
        )
        column = int(
            round((lookup_lon - plot_config.lon_range[0]) / plot_config.interp_step)
        )
        row = int(
            round((lat_value - plot_config.lat_range[0]) / plot_config.interp_step)
        )
        display_lon = (lon_value + 180.0) % 360.0 - 180.0
        if 0 <= row < time_grid.shape[0] and 0 <= column < time_grid.shape[1]:
            time_value = time_grid[row, column]
        else:
            time_value = np.nan
        return (
            f"经度={display_lon:.2f}°, 纬度={lat_value:.2f}°, "
            f"通信时长={time_value:.2f} h"
        )

    axes.format_coord = format_coordinates
    print(
        f"[绘图] 全球通信时长图完成，max = {max_hour:.3f} h, "
        f"step = {level_step:.3f} h"
    )
    if standalone:
        axes.figure.tight_layout()
    return axes


def _nice_level_step(max_hour: float) -> tuple[float, float]:
    if not np.isfinite(max_hour) or max_hour <= 0:
        return 1.0, 1.0

    raw_step = max_hour / 8.0
    base = 10.0 ** np.floor(np.log10(raw_step))
    ratio = raw_step / base
    if ratio <= 1:
        nice_ratio = 1.0
    elif ratio <= 2:
        nice_ratio = 2.0
    elif ratio <= 5:
        nice_ratio = 5.0
    else:
        nice_ratio = 10.0

    level_step = nice_ratio * base
    max_level = np.ceil(max_hour / level_step) * level_step
    return float(level_step), float(max_level)


def _read_satellite_track(satellite, scenario, plot_config):
    provider = satellite.DataProviders.Item("LLA State").Group.Item("Fixed")
    result = provider.Exec(
        scenario.StartTime, scenario.StopTime, plot_config.track_step
    )
    latitude = numeric_dataset(result, "Lat")
    longitude = numeric_dataset(result, "Lon")
    longitude = (
        np.mod(longitude - plot_config.lon_range[0], 360.0)
        + plot_config.lon_range[0]
    )
    jumps = np.concatenate(
        [[False], np.abs(np.diff(longitude)) > 180.0]
    )
    latitude[jumps] = np.nan
    longitude[jumps] = np.nan
    return latitude, longitude


def _remove_existing_colorbar(axes) -> None:
    colorbar = getattr(axes, "_stk_colorbar", None)
    if colorbar is not None:
        colorbar.remove()
        delattr(axes, "_stk_colorbar")
