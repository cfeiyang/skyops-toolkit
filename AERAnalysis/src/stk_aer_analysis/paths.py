"""源码与可执行文件共用的路径规则。"""

from __future__ import annotations

import sys
from pathlib import Path


def application_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def package_resource(*parts: str) -> Path:
    """Return a bundled resource path in source and PyInstaller modes."""
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS) / "stk_aer_analysis"
    else:
        base = Path(__file__).resolve().parent
    return base.joinpath(*parts)
