"""全球覆盖通信时长仿真的命令行入口。"""

from __future__ import annotations

import argparse

import matplotlib.pyplot as plt

from stk_simulation.simulations.global_coverage.config import config_global_coverage
from stk_simulation.simulations.global_coverage.service import (
    render_global_coverage,
    run_document_scenarios,
    run_global_coverage,
)
from stk_simulation.stk.session import STKSession


def main() -> int:
    parser = argparse.ArgumentParser(description="STK 全球覆盖通信时长仿真")
    parser.add_argument(
        "--stk-mode",
        choices=("new", "running"),
        default="new",
        help="新建 STK 或连接已运行 STK",
    )
    parser.add_argument(
        "--document-scenarios",
        action="store_true",
        help="运行仿真场景文档规定的全部方案和海外站增量对比",
    )
    args = parser.parse_args()

    config = config_global_coverage()
    config.stk.mode = args.stk_mode
    session = STKSession()
    root = session.connect(args.stk_mode)
    if args.document_scenarios:
        result = run_document_scenarios(root, config, print)
        render_global_coverage(result)
    else:
        result = run_global_coverage(root, config)

    print(f"卫星数量 = {result.summary.satellite_count}")
    print(f"地面站数量 = {result.summary.station_count}")
    print(f"最大通信时长 = {result.summary.max_hour:.3f} h")
    for image_path in result.additional_images or (result.output.image_path,):
        print(f"图片 = {image_path}")
    plt.show()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
