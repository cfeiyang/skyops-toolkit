"""STKSimulation 图形界面入口。"""

from __future__ import annotations

import sys

def main() -> int:
    print("[启动] 正在打开 STK 卫星通信仿真界面...", flush=True)
    import matplotlib

    matplotlib.use("QtAgg")

    from stk_simulation.app.application import run_application

    return run_application()


if __name__ == "__main__":
    sys.exit(main())
