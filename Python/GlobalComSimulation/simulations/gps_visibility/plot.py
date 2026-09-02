from __future__ import annotations

import matplotlib.pyplot as plt

from simulations.global_coverage.plot import configure_chinese_font


def plot_gps_visibility(result, cfg, ax=None):
    configure_chinese_font()
    standalone = ax is None
    if standalone:
        _, ax = plt.subplots(figsize=(12, 6), facecolor="white")
    else:
        ax.clear()

    data = result.gps_count_data
    ax.step(data["ElapsedHour"], data["GPSCount"], where="post", linewidth=1.5, color=(0, 0.35, 0.75))
    ax.grid(True)
    ax.set_xlabel("时间 / h")
    ax.set_ylabel("GPS卫星数量")
    ax.set_xlim(0, 24)
    ax.set_xticks(range(0, 25, 2))
    y_max = max(1, result.summary.max_count + 1)
    ax.set_ylim(0, y_max)
    ax.set_yticks(range(0, y_max + 1))
    if getattr(cfg.plot, "title", ""):
        ax.set_title(cfg.plot.title)
    print(
        f"[绘图] GPS可见数量图完成，范围={result.summary.min_count}至{result.summary.max_count}颗"
    )
    if standalone:
        ax.figure.tight_layout()
    return ax
