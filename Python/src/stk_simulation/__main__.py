"""STKSimulation 图形界面入口。"""

from __future__ import annotations

import sys

import matplotlib

matplotlib.use("QtAgg")

from stk_simulation.app.application import run_application


def main() -> int:
    return run_application()


if __name__ == "__main__":
    sys.exit(main())
