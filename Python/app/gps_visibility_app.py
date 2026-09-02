"""单星 GPS 可见数量桌面应用。"""

from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import matplotlib

matplotlib.use("TkAgg")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.async_stk_app import AsyncSTKApp
from app.panels.gps_visibility_panel import GPSVisibilityPanel
from app.ui import PlotView, configure_window
from setup_project import setup_project
from simulations.gps_visibility.config import config_gps_visibility
from simulations.gps_visibility.run_gps_visibility import (
    compute_gps_visibility,
    render_gps_visibility,
)
from utils.plotting import save_axes_image


class GPSVisibilityApp(AsyncSTKApp):
    def __init__(self):
        setup_project(PROJECT_ROOT)
        self.window = tk.Tk()
        configure_window(self.window, "GPS 可见数量仿真", "1380x780")
        super().__init__(self.window)
        self.last_result = None

        split = ttk.Panedwindow(self.window, orient=tk.HORIZONTAL)
        split.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        parameter_frame = ttk.LabelFrame(split, text="参数配置")
        result_frame = ttk.LabelFrame(split, text="GPS 可见数量")
        split.add(parameter_frame, weight=0)
        split.add(result_frame, weight=1)

        self.panel = GPSVisibilityPanel(
            parameter_frame, config_gps_visibility()
        )
        self.plot_view = PlotView(result_frame, self.save_image)
        self.panel.run_button.configure(command=self.run_simulation)
        self.window.after_idle(lambda: split.sashpos(0, 480))

    def run_simulation(self) -> None:
        try:
            config = self.panel.read_config()
        except Exception as error:
            messagebox.showerror("参数错误", str(error), parent=self.window)
            return

        self._set_busy(True, "正在加载 GPS 星座并计算...")

        def task():
            return compute_gps_visibility(
                self.get_stk_root(config.stk.mode), config
            )

        self.submit(task, self._show_result, self._show_error)

    def _show_result(self, result) -> None:
        self.last_result = result
        render_gps_visibility(result, self.plot_view.axes)
        self.plot_view.draw()
        self.plot_view.set_result_available()
        self._set_busy(False, f"完成 · {result.output.image_path}")

    def _show_error(self, error: Exception) -> None:
        self._set_busy(False, "仿真失败")
        messagebox.showerror("仿真错误", str(error), parent=self.window)

    def _set_busy(self, busy: bool, status: str) -> None:
        self.panel.set_busy(busy)
        self.panel.set_status(status)
        self.plot_view.set_result_available(not busy and self.last_result is not None)
        self.window.configure(cursor="watch" if busy else "")

    def save_image(self) -> None:
        if self.last_result is None:
            return
        output = self.last_result.output
        selected = filedialog.asksaveasfilename(
            parent=self.window,
            title="保存结果图",
            defaultextension=".png",
            initialdir=str(output.result_dir),
            initialfile=output.image_name,
            filetypes=[("PNG 图片", "*.png")],
        )
        if selected:
            save_axes_image(self.plot_view.axes, selected)
            self.panel.set_status(f"图片已保存 · {selected}")

    def run(self) -> None:
        self.window.mainloop()


if __name__ == "__main__":
    GPSVisibilityApp().run()
