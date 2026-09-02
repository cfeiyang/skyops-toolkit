"""GPS 可见数量命令行入口，对应 MATLAB/gps_visibility/run.m。"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import matplotlib.pyplot as plt

from setup_project import setup_project
from simulations.gps_visibility.config import config_gps_visibility
from simulations.gps_visibility.run_gps_visibility import run_gps_visibility
from stk_api.core import STKCore


def main():
    setup_project(PROJECT_ROOT)
    config = config_gps_visibility()
    application, root = STKCore.start_stk(config.stk.mode)
    result = run_gps_visibility(root, config)

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
    plt.show()
    return application, result


if __name__ == "__main__":
    main()
