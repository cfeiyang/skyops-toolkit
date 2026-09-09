"""桌面程序入口。"""

from __future__ import annotations

import sys

from stk_aer_analysis.app import run_application


def main() -> int:
    return run_application()


if __name__ == "__main__":
    sys.exit(main())

