"""全球通信时长桌面应用。"""

from __future__ import annotations

import copy
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import matplotlib

matplotlib.use("TkAgg")

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.async_stk_app import AsyncSTKApp
from app.panels.global_coverage_panel import GlobalCoveragePanel
from app.ui import PlotView, configure_window
from setup_project import setup_project
from simulations.global_coverage.config import config_global_coverage
from simulations.global_coverage.run_global_coverage import (
    compute_global_coverage,
    render_global_coverage,
)
from simulations.global_coverage.templates import station_template
from utils.plotting import save_axes_image


class GlobalCoverageApp(AsyncSTKApp):
    def __init__(self):
        setup_project(PROJECT_ROOT)
        self.window = tk.Tk()
        configure_window(self.window, "全球通信时长仿真", "1480x820")
        super().__init__(self.window)

        self.last_result = None
        split = ttk.Panedwindow(self.window, orient=tk.HORIZONTAL)
        split.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        parameter_frame = ttk.LabelFrame(split, text="参数配置")
        result_frame = ttk.LabelFrame(split, text="全球通信时长")
        split.add(parameter_frame, weight=0)
        split.add(result_frame, weight=1)

        self.panel = GlobalCoveragePanel(
            parameter_frame, config_global_coverage()
        )
        self.plot_view = PlotView(result_frame, self.save_image)
        self.panel.run_button.configure(command=self.run_simulation)
        self.panel.run_all_button.configure(command=self.run_all_simulations)
        self.window.after_idle(lambda: split.sashpos(0, 510))

    def run_simulation(self) -> None:
        try:
            config = self.panel.read_config()
        except Exception as error:
            messagebox.showerror("参数错误", str(error), parent=self.window)
            return

        self._set_busy(True, "正在连接 STK 并计算覆盖...")

        def task():
            return compute_global_coverage(
                self.get_stk_root(config.stk.mode), config
            )

        self.submit(task, self._show_result, self._show_error)

    def run_all_simulations(self) -> None:
        try:
            base_config = self.panel.read_config()
        except Exception as error:
            messagebox.showerror("参数错误", str(error), parent=self.window)
            return

        self._set_busy(True, "准备运行全部 8 组方案...")

        def task():
            root = self.get_stk_root(base_config.stk.mode)
            last_result = None
            combinations = [
                (satellite_mode, station_mode, satellite_label, station_label)
                for satellite_mode, satellite_label in (
                    ("single", "单星"),
                    ("multi", "多星"),
                )
                for station_mode, station_label in (
                    ("single", "单站"),
                    ("two", "双站"),
                    ("three", "三站"),
                    ("four", "四站"),
                )
            ]
            for index, (sat_mode, station_mode, sat_label, station_label) in enumerate(
                combinations, start=1
            ):
                self.post(
                    self.panel.set_status,
                    f"自动仿真 {index}/8：{sat_label}{station_label}",
                )
                config = copy.deepcopy(base_config)
                config.satellite_group.mode = sat_mode
                config.stations = station_template(station_mode)
                config.output.image_name = ""
                last_result = compute_global_coverage(root, config)
                _render_offscreen(last_result)
                if root.CurrentScenario is not None:
                    root.CloseScenario()
            return last_result

        self.submit(task, self._show_batch_result, self._show_error)

    def _show_result(self, result) -> None:
        self.last_result = result
        render_global_coverage(result, self.plot_view.axes)
        self.plot_view.draw()
        self.plot_view.set_result_available()
        self._set_busy(False, f"完成 · {result.output.image_path}")

    def _show_batch_result(self, result) -> None:
        self.last_result = result
        render_global_coverage(result, self.plot_view.axes)
        self.plot_view.draw()
        self.plot_view.set_result_available()
        self._set_busy(False, f"全部 8 组完成 · {result.output.result_dir}")

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


def _render_offscreen(result) -> None:
    """批处理在工作线程保存图片，不触碰 Tk 画布。"""
    figure = Figure(figsize=(14, 6.5), facecolor="white", layout="constrained")
    FigureCanvasAgg(figure)
    render_global_coverage(result, figure.add_subplot(111))
    figure.clear()


if __name__ == "__main__":
    GlobalCoverageApp().run()
