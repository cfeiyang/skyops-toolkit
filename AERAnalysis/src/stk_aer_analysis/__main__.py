"""桌面程序入口。"""

from __future__ import annotations

import sys


def main() -> int:
    import matplotlib

    matplotlib.use("QtAgg")

    from stk_aer_analysis.app import run_application

    return run_application()


if __name__ == "__main__":
    sys.exit(main())
