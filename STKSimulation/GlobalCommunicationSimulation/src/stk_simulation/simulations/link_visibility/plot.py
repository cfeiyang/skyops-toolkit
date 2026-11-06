"""星地建链与 AER 预报的三种 Matplotlib 可视化图表。"""

from __future__ import annotations

from datetime import datetime
import matplotlib.dates as mdates
import numpy as np

from stk_simulation.simulations.link_visibility.config import LinkVisibilityResult
from stk_simulation.utils.plotting import configure_chinese_font

TIME_FMT = "%Y-%m-%d %H:%M:%S"


def plot_elevation_curve(result: LinkVisibilityResult, figure) -> None:
    """视图 1：绘制过境仰角-时间曲线。"""
    configure_chinese_font()
    figure.clear()
    ax = figure.add_subplot(111)

    if not result.aer_records:
        ax.text(0.5, 0.5, "当前时段内无满足约束的可见窗口", ha="center", va="center", fontsize=12)
        return

    for st_name in result.station_names:
        pts = [r for r in result.aer_records if r.station_name == st_name]
        if not pts:
            continue
        times = [datetime.strptime(r.time, TIME_FMT) for r in pts]
        els = [r.elevation_deg for r in pts]
        ax.plot(times, els, "o-", markersize=3, linewidth=1.6, label=st_name)

    ax.axhline(
        result.cfg.stations[0].min_elevation_deg,
        color="#dc2626",
        linestyle="--",
        linewidth=1.0,
        label="最低仰角门限",
    )
    ax.set_title(f"{result.satellite_name} 建链可见窗口仰角曲线 ({result.engine_used.upper()} 引擎)")
    ax.set_xlabel("北京时间")
    ax.set_ylabel("仰角 (°)")
    ax.grid(True, linestyle=":", alpha=0.6)
    ax.legend(loc="upper right")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))


def plot_skyplot_polar(result: LinkVisibilityResult, figure) -> None:
    """视图 2：绘制极坐标天空轨迹图 (Skyplot)。"""
    configure_chinese_font()
    figure.clear()
    ax = figure.add_subplot(111, projection="polar")
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)
    ax.set_rlim(0, 90)
    ax.set_rticks([15, 30, 60, 90])
    ax.set_yticklabels(["75°", "60°", "30°", "0°(地平)"])

    for acc in result.windows:
        pts = [r for r in result.aer_records if r.access_number == acc.access_number]
        if not pts:
            continue
        theta = np.deg2rad([r.azimuth_deg for r in pts])
        r_zenith = [90.0 - r.elevation_deg for r in pts]
        ax.plot(theta, r_zenith, linewidth=2.0, label=f"圈次 #{acc.access_number}")
        ax.scatter(theta[0], r_zenith[0], marker="^", s=45)
        ax.scatter(theta[-1], r_zenith[-1], marker="v", s=45)

    ax.set_title(f"{result.satellite_name} 站心极坐标天空轨迹图 (北=0°, 中心=天顶90°)", pad=18)
    if result.windows:
        ax.legend(loc="upper right", bbox_to_anchor=(1.25, 1.05))


def plot_ground_track_2d(result: LinkVisibilityResult, figure) -> None:
    """视图 3：绘制星下点地面轨迹与建链高亮段。"""
    configure_chinese_font()
    figure.clear()
    ax = figure.add_subplot(111)

    lons = np.array([p.longitude_deg for p in result.ground_track])
    lats = np.array([p.latitude_deg for p in result.ground_track])
    linked = np.array([p.linked for p in result.ground_track], dtype=bool)

    jumps = np.concatenate(([False], np.abs(np.diff(lons)) > 180.0))
    lons_plot = np.where(jumps, np.nan, lons)
    lats_plot = np.where(jumps, np.nan, lats)

    ax.plot(lons_plot, lats_plot, color="#94a3b8", linewidth=1.2, label="星下点轨迹 (不可见)")
    if np.any(linked):
        ax.scatter(
            lons[linked],
            lats[linked],
            color="#16a34a",
            s=18,
            zorder=4,
            label="可建链区段 (满足仰角/GSO)",
        )

    for st in result.cfg.stations[: len(result.station_names)]:
        ax.scatter(
            st.longitude_deg,
            st.latitude_deg,
            color="#dc2626",
            marker="^",
            s=90,
            zorder=5,
            label=f"地面站: {st.name}",
        )

    ax.set_xlim(-180, 180)
    ax.set_ylim(-90, 90)
    ax.set_xlabel("经度 (°)")
    ax.set_ylabel("纬度 (°)")
    ax.set_title(f"{result.satellite_name} 星下点轨迹与建链弧段分布")
    ax.grid(True, linestyle="--", alpha=0.5)
    ax.legend(loc="lower left")
