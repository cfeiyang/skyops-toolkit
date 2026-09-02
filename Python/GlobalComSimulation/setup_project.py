"""把项目根目录加入 sys.path，对应 MATLAB 的 setupProject.m。"""

from __future__ import annotations

import sys
from pathlib import Path


def setup_project(project_root: str | Path | None = None) -> Path:
    root = Path(project_root).resolve() if project_root else Path(__file__).resolve().parent
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    print(f"[PATH] 项目共享代码路径已配置：{root}")
    return root


def project_root() -> Path:
    return Path(__file__).resolve().parent
