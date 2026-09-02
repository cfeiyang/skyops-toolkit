from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from setup_project import setup_project
from simulations.global_coverage.config import config_global_coverage
from simulations.global_coverage.run_global_coverage import run_global_coverage
from stk_api.core import STKCore


def main():
    setup_project(ROOT)
    cfg = config_global_coverage()
    app, root = STKCore.start_stk(cfg.stk.mode)
    result = run_global_coverage(root, cfg)
    print()
    print("========================================")
    print(" GLOBAL COVERAGE")
    print("========================================")
    print(f"卫星数量 = {result.summary.satellite_count}")
    print(f"地面站数量 = {result.summary.station_count}")
    print(f"最大通信时长 = {result.summary.max_hour:.3f} h")
    print(f"图片 = {result.output.image_path}")
    print("========================================")
    return app, result


if __name__ == "__main__":
    main()
