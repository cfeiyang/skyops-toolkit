"""两个仿真功能的统一命令行入口。"""

from __future__ import annotations

import argparse

import matplotlib.pyplot as plt

from stk_simulation.simulations.global_coverage.config import config_global_coverage
from stk_simulation.simulations.global_coverage.service import run_global_coverage
from stk_simulation.simulations.gps_visibility.config import config_gps_visibility
from stk_simulation.simulations.gps_visibility.service import run_gps_visibility
from stk_simulation.stk.session import STKSession


def main() -> int:
    parser = argparse.ArgumentParser(description="STK 卫星通信仿真")
    parser.add_argument(
        "feature",
        choices=("global-coverage", "gps-visibility"),
        help="需要运行的仿真功能",
    )
    parser.add_argument(
        "--stk-mode",
        choices=("new", "running"),
        default="new",
        help="新建 STK 或连接已运行 STK",
    )
    args = parser.parse_args()

    session = STKSession()
    root = session.connect(args.stk_mode)
    if args.feature == "global-coverage":
        config = config_global_coverage()
        config.stk.mode = args.stk_mode
        result = run_global_coverage(root, config)
        print(f"卫星数量 = {result.summary.satellite_count}")
        print(f"地面站数量 = {result.summary.station_count}")
        print(f"最大通信时长 = {result.summary.max_hour:.3f} h")
    else:
        config = config_gps_visibility()
        config.stk.mode = args.stk_mode
        result = run_gps_visibility(root, config)
        print(f"GPS 卫星总数 = {result.summary.gps_total}")
        print(f"最小可见数量 = {result.summary.min_count}")
        print(f"最大可见数量 = {result.summary.max_count}")
        print(f"平均可见数量 = {result.summary.mean_count:.3f}")

    print(f"图片 = {result.output.image_path}")
    plt.show()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
