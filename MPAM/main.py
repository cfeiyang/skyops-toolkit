"""月度项目分配管理（MPAM）—— 入口。

启动流程：
1. 先出登录界面（默认账号 root / 密码 123456，可在 config.json 修改）；
2. 登录后进入主界面（**不弹文件选择框**），等你手动点「导入 Excel…」；
3. 选定文件后读入月份表头与人员，之后所有分配/修改直接写回该文件
   （自动备份 + 原子保存）。

用法：
    python main.py            登录 → 主界面 → 手动导入文件
    python main.py --mock     调试：跳过导入，直接加载内置模拟数据（仍需登录）
    python main.py --reset    把模拟表移到 backup/ 后重新生成（配合 --mock）
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# pythonw.exe 启动时没有控制台，stdout/stderr 为 None；重定向到空设备，避免 print 抛异常
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

BASE = Path(__file__).resolve().parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

DATA_DIR = BASE / "data"
WORKBOOK = DATA_DIR / "月度项目分配-模拟.xlsx"


def _require_dependencies() -> bool:
    try:
        import openpyxl  # noqa: F401
    except ImportError:
        print("[错误] 缺少 openpyxl。请执行：")
        print("       python -m pip install openpyxl")
        _alert("缺少依赖", "缺少 openpyxl，请先执行：\n\npython -m pip install openpyxl")
        return False
    return True


def _alert(title: str, text: str) -> None:
    """pythonw 下没有控制台，用弹窗把错误显示出来。"""
    try:
        from tkinter import Tk, messagebox

        root = Tk()
        root.withdraw()
        messagebox.showerror(title, text)
        root.destroy()
    except Exception:
        print(f"[错误] {text}")


def _reset_mock() -> None:
    if not WORKBOOK.exists():
        return
    folder = DATA_DIR / "backup"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = folder / f"{WORKBOOK.stem}_重置前_{stamp}{WORKBOOK.suffix}"
    WORKBOOK.replace(target)
    print(f"[重置] 原文件已移到 {target}")


def main(argv=None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not _require_dependencies():
        return 2

    from excel_store import AssignError, ExcelStore
    from mock_data import ensure_mock_workbook

    store: Optional[ExcelStore] = None
    if "--mock" in arguments:
        if "--reset" in arguments:
            _reset_mock()
        ensure_mock_workbook(WORKBOOK)
        try:
            store = ExcelStore(str(WORKBOOK)).load()
        except AssignError as error:
            print(f"[错误] {error}")
            _alert("打开失败", str(error))
            return 1
        except Exception as error:  # 文件损坏、不是 xlsx 等
            print(f"[错误] {type(error).__name__}: {error}")
            _alert("打开失败", f"{type(error).__name__}: {error}")
            return 1
        if store.duplicate_people:
            print(f"[提示] 汇总表里有重名人员：{'、'.join(store.duplicate_people)}")

    try:
        import ui
    except ImportError as error:  # 极少见：Python 安装时没带 tkinter
        print(f"[错误] 无法加载界面模块（tkinter）：{error}")
        _alert("界面加载失败", f"无法加载 tkinter：{error}")
        return 3

    # 不带 --mock 时以空态启动：登录 → 主界面 → 用户手动点「导入 Excel…」
    ui.run(store)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
