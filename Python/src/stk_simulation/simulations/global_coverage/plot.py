"""全球通信时长 Behrmann 等面积投影图。"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.basemap import Basemap
from scipy.interpolate import LinearNDInterpolator

from stk_simulation.utils.plotting import (
    configure_chinese_font,
    parula_colormap,
)


def plot_global_coverage(result, config, axes=None):
    configure_chinese_font()
    plot = config.plot
    coverage = result.coverage_data

    latitude = coverage["LatitudeDeg"].to_numpy(dtype=float)
    longitude = np.mod(coverage["LongitudeDeg"].to_numpy(dtype=float), 360.0)
    time_hours = coverage["TimeHour"].to_numpy(dtype=float)
    finite_time = time_hours[np.isfinite(time_hours)]
    max_hour = float(finite_time.max()) if finite_time.size else float("nan")
    level_step, max_level = _nice_level_step(max_hour)
    levels = np.arange(0.0, max_level + level_step * 0.5, level_step)

    # Basemap/PROJ 会把相差 360° 的首尾经度视为同一条经线。
    # 全球网格不重复加入右端点，避免地图宽度退化为接近 0。
    grid_longitudes = np.arange(
        plot.lon_range[0], plot.lon_range[1], plot.interp_step
    )
    longitude_grid, latitude_grid = np.meshgrid(
        grid_longitudes,
        np.arange(
            plot.lat_range[0],
            plot.lat_range[1] + plot.interp_step * 0.5,
            plot.interp_step,
        ),
    )
    time_grid = _interpolate_periodic(
        longitude, latitude, time_hours, longitude_grid, latitude_grid
    )
    time_grid[time_grid <= 0] = np.nan

    standalone = axes is None
    if standalone:
        _, axes = plt.subplots(figsize=(14, 6.5), facecolor="white")
    else:
        _remove_existing_colorbar(axes)
        axes.clear()
    axes.set_axis_on()

    world_map = Basemap(
        projection="cea",
        lat_ts=30,
        lon_0=plot.center_lon,
        llcrnrlon=plot.lon_range[0],
        urcrnrlon=float(grid_longitudes[-1]),
        llcrnrlat=plot.lat_range[0],
        urcrnrlat=plot.lat_range[1],
        resolution="c",
        ax=axes,
    )
    x_grid, y_grid = world_map(longitude_grid, latitude_grid)
    filled = axes.contourf(
        x_grid,
        y_grid,
        time_grid,
        levels=levels,
        cmap=parula_colormap(),
        vmin=0.0,
        vmax=max_level,
        antialiased=True,
    )
    contour = axes.contour(
        x_grid,
        y_grid,
        time_grid,
        levels=levels[1:],
        colors="#404040",
        linewidths=0.5,
    )
    if plot.show_contour_labels and levels.size > 1:
        axes.clabel(contour, inline=True, fontsize=9, fmt="%.2g")

    world_map.drawcoastlines(color="black", linewidth=1.0)
    track_colors = plt.colormaps["tab10"](
        np.linspace(0.0, 1.0, max(len(result.satellite_tracks), 1))
    )
    for index, (track_latitude, track_longitude) in enumerate(
        result.satellite_tracks
    ):
        track_x, track_y = world_map(track_longitude, track_latitude)
        axes.plot(track_x, track_y, color=track_colors[index], linewidth=1.3)

    stations = result.cfg.stations
    station_colors = plt.colormaps["tab10"](
        np.linspace(0.0, 1.0, max(len(stations), 1))
    )
    for index, station in enumerate(stations):
        station_x, station_y = world_map(station.lon, station.lat)
        axes.plot(
            station_x,
            station_y,
            marker="o",
            linestyle="none",
            markersize=8,
            markerfacecolor=station_colors[index],
            markeredgecolor="black",
        )
        axes.annotate(
            station.name,
            (station_x, station_y),
            xytext=(5, 0),
            textcoords="offset points",
            va="center",
            fontsize=10,
            fontweight="bold",
        )

    x_min = float(np.nanmin(x_grid))
    x_max = float(np.nanmax(x_grid))
    y_min = float(np.nanmin(y_grid))
    y_max = float(np.nanmax(y_grid))
    longitude_fraction = (
        np.asarray(plot.lon_ticks, dtype=float) - plot.lon_range[0]
    ) / (plot.lon_range[1] - plot.lon_range[0])
    tick_x = x_min + longitude_fraction * (x_max - x_min)
    _, tick_y = world_map(
        np.full(len(plot.lat_ticks), plot.center_lon), np.asarray(plot.lat_ticks)
    )
    axes.set_xticks(tick_x, labels=plot.lon_tick_labels)
    axes.set_yticks(tick_y, labels=plot.lat_tick_labels)
    axes.set_xlim(x_min, x_max)
    axes.set_ylim(y_min, y_max)
    axes.set_aspect("equal", adjustable="box")
    axes.grid(True, linestyle=":", alpha=0.25)
    axes.set_xlabel("经度/°")
    axes.set_ylabel("纬度/°")

    colorbar = axes.figure.colorbar(
        filled, ax=axes, orientation="vertical", fraction=0.03, pad=0.02
    )
    colorbar.set_ticks(levels)
    colorbar.set_label("通信时长 / h")
    axes._stk_colorbar = colorbar  # type: ignore[attr-defined]
    if plot.title:
        axes.set_title(plot.title, fontweight="normal")

    axes.format_coord = _coordinate_formatter(
        world_map, time_grid, plot.lon_range, plot.lat_range, plot.interp_step
    )
    print(
        f"[绘图] 全球通信时长图完成，max = {max_hour:.3f} h, "
        f"step = {level_step:.3f} h"
    )
    if standalone:
        axes.figure.tight_layout()
    return axes


def _interpolate_periodic(longitude, latitude, values, grid_lon, grid_lat):
    extended_points = np.column_stack(
        (
            np.concatenate((longitude - 360.0, longitude, longitude + 360.0)),
            np.tile(latitude, 3),
        )
    )
    extended_values = np.tile(values, 3)
    valid = np.isfinite(extended_points).all(axis=1) & np.isfinite(extended_values)
    interpolator = LinearNDInterpolator(
        extended_points[valid], extended_values[valid], fill_value=np.nan
    )
    return interpolator(grid_lon, grid_lat)


def _nice_level_step(max_hour: float) -> tuple[float, float]:
    if not np.isfinite(max_hour) or max_hour <= 0:
        return 1.0, 1.0
    raw_step = max_hour / 8.0
    base = 10.0 ** np.floor(np.log10(raw_step))
    ratio = raw_step / base
    nice_ratio = next(value for value in (1.0, 2.0, 5.0, 10.0) if ratio <= value)
    step = nice_ratio * base
    return float(step), float(np.ceil(max_hour / step) * step)


def _coordinate_formatter(world_map, time_grid, lon_range, lat_range, step):
    def format_coordinates(x_value: float, y_value: float) -> str:
        longitude, latitude = world_map(x_value, y_value, inverse=True)
        lookup_lon = (longitude - lon_range[0]) % 360.0 + lon_range[0]
        column = round((lookup_lon - lon_range[0]) / step)
        row = round((latitude - lat_range[0]) / step)
        value = (
            time_grid[row, column]
            if 0 <= row < time_grid.shape[0] and 0 <= column < time_grid.shape[1]
            else np.nan
        )
        display_lon = (longitude + 180.0) % 360.0 - 180.0
        return (
            f"经度={display_lon:.2f}°, 纬度={latitude:.2f}°, "
            f"通信时长={value:.2f} h"
        )

    return format_coordinates


def _remove_existing_colorbar(axes) -> None:
    colorbar = getattr(axes, "_stk_colorbar", None)
    if colorbar is not None:
        colorbar.remove()
        delattr(axes, "_stk_colorbar")
