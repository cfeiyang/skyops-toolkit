from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from setup_project import setup_project
from simulations.gps_visibility.config import config_gps_visibility
from simulations.gps_visibility.run_gps_visibility import run_gps_visibility
from stk_api.core import STKCore


def main():
    setup_project(ROOT)
    cfg = config_gps_visibility()
    _app, root = STKCore.start_stk(cfg.stk.mode)
    result = run_gps_visibility(root, cfg)
    print()
    print("========================================")
    print(" GPS VISIBILITY")
    print("========================================")
    print(f"GPS卫星总数 = {result.summary.gps_total}")
    print(f"最小可见数量 = {result.summary.min_count}")
    print(f"最大可见数量 = {result.summary.max_count}")
    print(f"平均可见数量 = {result.summary.mean_count:.3f}")
    print(f"图片 = {result.output.image_path}")
    print("========================================")
    return result


if __name__ == "__main__":
    main()
