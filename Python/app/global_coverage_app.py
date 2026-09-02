"""全球通信时长独立 GUI，对应 MATLAB/GlobalCoverageApp.m。"""

from __future__ import annotations

import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import matplotlib

matplotlib.use("TkAgg")

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.panels.global_coverage_panel import GlobalCoveragePanel
from setup_project import setup_project
from simulations.global_coverage.config import config_global_coverage
from simulations.global_coverage.plot_global_coverage import save_axes_image
from simulations.global_coverage.run_global_coverage import run_global_coverage
from simulations.global_coverage.templates import station_template
from stk_api.core import STKCore


class GlobalCoverageApp:
    def __init__(self):
        setup_project(PROJECT_ROOT)
        self.config = config_global_coverage()
        self.stk_application = None
        self.stk_root = None
        self.last_result = None

        self.window = tk.Tk()
        self.window.title("全球通信时长仿真")
        self.window.geometry("1500x800")
        self.window.minsize(1100, 650)

        self.window.columnconfigure(0, minsize=560)
        self.window.columnconfigure(1, weight=1)
        self.window.rowconfigure(0, weight=1)

        parameter_frame = ttk.LabelFrame(
            self.window, text="全球通信时长参数"
        )
        parameter_frame.grid(
            row=0, column=0, sticky="nsew", padx=(10, 5), pady=10
        )
        self.panel = GlobalCoveragePanel(parameter_frame, self.config)

        result_frame = ttk.LabelFrame(
            self.window, text="全球通信时长梯度图"
        )
        result_frame.grid(
            row=0, column=1, sticky="nsew", padx=(5, 10), pady=10
        )
        self._build_result_panel(result_frame)

        self.panel.run_button.configure(command=self.run_simulation)
        self.panel.run_all_button.configure(command=self.run_all_simulations)

    def _build_result_panel(self, parent) -> None:
        self.figure = Figure(figsize=(9, 6.5), facecolor="white")
        self.axes = self.figure.add_subplot(111)
        self._show_waiting_state()
        self.canvas = FigureCanvasTkAgg(self.figure, master=parent)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        self.save_button = ttk.Button(
            parent,
            text="保存图片",
            command=self.save_image,
            state=tk.DISABLED,
        )
        self.save_button.pack(fill=tk.X, padx=8, pady=8)

    def run_simulation(self) -> None:
        self.panel.run_button.configure(state=tk.DISABLED)
        self.save_button.configure(state=tk.DISABLED)
        try:
            run_config = self.panel.read_config()
            self.panel.set_status("状态：正在连接STK...")
            self._ensure_stk(run_config.stk.mode)

            self.panel.set_status("状态：正在仿真...")
            self.last_result = run_global_coverage(
                self.stk_root, run_config, self.axes
            )
            self.canvas.draw()
            self.save_button.configure(state=tk.NORMAL)
            self.panel.set_status(
                f"状态：完成，图片已保存到 "
                f"{self.last_result.output.image_path}"
            )
        except Exception as error:
            self.panel.set_status("状态：仿真失败")
            messagebox.showerror("仿真错误", str(error), parent=self.window)
        finally:
            self.panel.run_button.configure(state=tk.NORMAL)

    def run_all_simulations(self) -> None:
        self.panel.run_button.configure(state=tk.DISABLED)
        self.panel.run_all_button.configure(state=tk.DISABLED)
        self.save_button.configure(state=tk.DISABLED)

        satellite_modes = ("single", "multi")
        station_modes = ("single", "two", "three", "four")
        satellite_labels = ("单星", "多星")
        station_labels = ("单站", "双站", "三站", "四站")
        total = len(satellite_modes) * len(station_modes)
        simulation_index = 0

        try:
            for satellite_index, satellite_mode in enumerate(satellite_modes):
                for station_index, station_mode in enumerate(station_modes):
                    simulation_index += 1
                    run_config = self.panel.read_config()
                    run_config.satellite_group.mode = satellite_mode
                    run_config.stations = station_template(station_mode)

                    self.panel.set_status(
                        f"状态：自动仿真 {simulation_index}/{total} "
                        f"({satellite_labels[satellite_index]}"
                        f"{station_labels[station_index]})..."
                    )
                    self._ensure_stk(run_config.stk.mode)
                    self.last_result = run_global_coverage(
                        self.stk_root, run_config, self.axes
                    )
                    self.canvas.draw()
                    self.panel.set_status(
                        f"状态：{simulation_index}/{total} 完成，"
                        f"图片 {self.last_result.output.image_path}"
                    )
                    self.window.update()

                    time.sleep(5)
                    if (
                        self.stk_root is not None
                        and self.stk_root.CurrentScenario is not None
                    ):
                        self.stk_root.CloseScenario()

            self.save_button.configure(state=tk.NORMAL)
            self.panel.set_status(
                f"状态：全部 {total} 组完成，图片保存到 "
                f"{self.last_result.output.result_dir}"
            )
        except Exception as error:
            self.panel.set_status("状态：自动仿真失败")
            messagebox.showerror("仿真错误", str(error), parent=self.window)
        finally:
            self.panel.run_button.configure(state=tk.NORMAL)
            self.panel.run_all_button.configure(state=tk.NORMAL)

    def save_image(self) -> None:
        if self.last_result is None:
            messagebox.showinfo("保存图片", "请先完成仿真。", parent=self.window)
            return

        default_path = (
            self.last_result.output.result_dir
            / self.last_result.output.image_name
        )
        selected_path = filedialog.asksaveasfilename(
            parent=self.window,
            title="选择保存目录和文件名",
            defaultextension=".png",
            initialdir=str(default_path.parent),
            initialfile=default_path.name,
            filetypes=[("PNG图片", "*.png")],
        )
        if not selected_path:
            return
        save_axes_image(self.axes, selected_path)
        self.panel.set_status(f"状态：图片已保存到 {selected_path}")

    def _ensure_stk(self, mode: str) -> None:
        if self.stk_root is None:
            self.stk_application, self.stk_root = STKCore.start_stk(mode)

    def _show_waiting_state(self) -> None:
        self.axes.clear()
        self.axes.set_title("等待仿真")
        self.axes.text(
            0.5,
            0.5,
            "设置参数后点击“开始仿真”",
            transform=self.axes.transAxes,
            horizontalalignment="center",
            verticalalignment="center",
            fontsize=14,
            color=(0.4, 0.4, 0.4),
        )
        self.axes.set_xticks([])
        self.axes.set_yticks([])

    def run(self) -> None:
        self.window.mainloop()


if __name__ == "__main__":
    GlobalCoverageApp().run()
