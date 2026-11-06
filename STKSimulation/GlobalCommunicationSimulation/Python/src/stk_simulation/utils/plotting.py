"""仿真绘图的字体、色图和文件输出工具。"""

from __future__ import annotations

import os
from pathlib import Path

import matplotlib
from matplotlib import font_manager
from matplotlib.colors import LinearSegmentedColormap


def configure_chinese_font() -> str:
    windows_fonts = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    for filename in ("msyh.ttc", "msyhbd.ttc", "simhei.ttf"):
        path = windows_fonts / filename
        if path.exists():
            try:
                font_manager.fontManager.addfont(str(path))
            except (OSError, RuntimeError):
                pass

    installed = {font.name for font in font_manager.fontManager.ttflist}
    candidates = (
        "Microsoft YaHei",
        "SimHei",
        "Noto Sans CJK SC",
        "Source Han Sans SC",
        "Arial Unicode MS",
    )
    selected = next((name for name in candidates if name in installed), "DejaVu Sans")
    matplotlib.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": [selected, "DejaVu Sans"],
            "axes.unicode_minus": False,
        }
    )
    return selected


def save_axes_image(axes, image_path: str | Path, dpi: int = 300) -> None:
    axes.figure.savefig(
        image_path, dpi=dpi, bbox_inches="tight", facecolor="white"
    )


def parula_colormap() -> LinearSegmentedColormap:
    """紧凑的 MATLAB Parula 色图近似。"""
    colors = (
        "#352a87",
        "#2450a4",
        "#1464b3",
        "#0878b7",
        "#078bb6",
        "#159cab",
        "#2aaa9f",
        "#47b78d",
        "#67c17c",
        "#8ac969",
        "#add05a",
        "#d0d64b",
        "#edda3c",
        "#f9d52f",
        "#f9c52a",
        "#f6ad24",
    )
    return LinearSegmentedColormap.from_list("parula", colors, N=256)
