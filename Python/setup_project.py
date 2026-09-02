"""配置 Python 工程路径，对应 MATLAB/setupProject.m。"""

from __future__ import annotations

import sys
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parent


def setup_project(root: str | Path | None = None) -> Path:
    resolved_root = Path(root).resolve() if root is not None else project_root()
    root_text = str(resolved_root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)
    print(f"[PATH] 项目共享代码路径已配置：{resolved_root}")
    return resolved_root
