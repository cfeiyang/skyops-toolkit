"""源码运行和可执行文件运行时的统一路径。"""

from __future__ import annotations

import sys
from pathlib import Path


def application_root() -> Path:
    """返回数据和结果目录所在的应用根目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[3]


def data_directory() -> Path:
    return application_root() / "data"


def result_directory(simulation_name: str) -> Path:
    return application_root() / "results" / simulation_name

