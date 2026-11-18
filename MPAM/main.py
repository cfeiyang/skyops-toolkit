"""启动月度项目分配。"""

from __future__ import annotations

import ctypes
import sys
from datetime import datetime


def show_startup_error(error: Exception) -> None:
    message = f"月度项目分配无法启动。\n\n{error}"
    if isinstance(error, ImportError):
        message += "\n\n请在 SkyOps 环境执行 python -m pip install -r requirements.txt。"
    if sys.platform == "win32":
        ctypes.windll.user32.MessageBoxW(None, message, "启动失败", 0x10)
    elif sys.stderr is not None:
        print(message, file=sys.stderr)


def main(argv=None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    try:
        from app import ui
        from app.database import Database, data_directory
        from app.mock_data import ensure_mock_workbook

        directory = data_directory()
        demo = None
        if "--mock" in arguments:
            directory /= "demo"
            if "--reset" in arguments:
                directory /= datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            demo = ensure_mock_workbook(directory / "月度项目分配-示例.xlsx")

        database = Database(directory / "allocations.sqlite3")
        try:
            return ui.run(database, demo)
        finally:
            database.close()
    except Exception as error:
        show_startup_error(error)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
