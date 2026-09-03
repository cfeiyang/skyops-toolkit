"""GPS 可见数量时序图，对应 MATLAB/plotGpsVisibility.m。"""

from __future__ import annotations

import matplotlib.pyplot as plt

from stk_simulation.utils.plotting import configure_chinese_font


def plot_gps_visibility(result, config, axes=None):
    configure_chinese_font()
    standalone = axes is None
    if standalone:
        _, axes = plt.subplots(figsize=(12, 6), facecolor="white")
    else:
        axes.clear()
    axes.set_axis_on()

    data = result.gps_count_data
    axes.step(
        data["ElapsedHour"],
        data["GPSCount"],
        where="post",
        linewidth=1.5,
        color=(0.0, 0.35, 0.75),
    )
    axes.grid(True)
    axes.set_xlabel("时间 / h")
    axes.set_ylabel("GPS卫星数量")
    axes.set_xlim(0, 24)
    axes.set_xticks(range(0, 25, 2))

    maximum_y = max(1, result.summary.max_count + 1)
    axes.set_ylim(0, maximum_y)
    axes.set_yticks(range(0, maximum_y + 1))

    if config.plot.title:
        axes.set_title(config.plot.title, fontweight="normal")

    print(
        f"[绘图] GPS可见数量图完成，范围="
        f"{result.summary.min_count}至{result.summary.max_count}颗"
    )
    if standalone:
        axes.figure.tight_layout()
    return axes
