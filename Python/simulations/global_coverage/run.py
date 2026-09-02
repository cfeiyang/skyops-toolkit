"""全球通信时长命令行入口，对应 MATLAB/global_coverage/run.m。"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import matplotlib.pyplot as plt

from setup_project import setup_project
from simulations.global_coverage.config import config_global_coverage
from simulations.global_coverage.run_global_coverage import run_global_coverage
from stk_api.core import STKCore


def main():
    setup_project(PROJECT_ROOT)
    config = config_global_coverage()
    application, root = STKCore.start_stk(config.stk.mode)
    result = run_global_coverage(root, config)

    print()
    print("========================================")
    print(" GLOBAL COVERAGE")
    print("========================================")
    print(f"卫星数量 = {result.summary.satellite_count}")
    print(f"地面站数量 = {result.summary.station_count}")
    print(f"最大通信时长 = {result.summary.max_hour:.3f} h")
    print(f"图片 = {result.output.image_path}")
    print("========================================")
    plt.show()
    return application, result


if __name__ == "__main__":
    main()
