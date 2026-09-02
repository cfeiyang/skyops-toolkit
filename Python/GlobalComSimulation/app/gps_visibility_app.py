from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import matplotlib

matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from setup_project import setup_project
from simulations.gps_visibility.config import config_gps_visibility
from simulations.gps_visibility.run_gps_visibility import run_gps_visibility
from stk_api.core import STKCore


STK_MODES = [("新建STK", "new"), ("连接已运行STK", "running")]


def _combo_value(combo: ttk.Combobox, items: list[tuple[str, str]]) -> str:
    label = combo.get()
    for text, value in items:
        if text == label:
            return value
    return items[0][1]


class GpsVisibilityApp:
    def __init__(self):
        setup_project(ROOT)
        self.cfg = config_gps_visibility()
        self.root_stk = None
        self.last_result = None

        self.win = tk.Tk()
        self.win.title("GPS可见数量仿真")
        self.win.geometry("1400x760")

        left = ttk.LabelFrame(self.win, text="单星GPS可见性参数")
        left.pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=10)
        right = ttk.LabelFrame(self.win, text="GPS可见数量时序图")
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=10, pady=10)

        self._build_panel(left)
        self._build_plot(right)
        self._write_cfg(self.cfg)

    def _build_panel(self, parent):
        form = ttk.Frame(parent)
        form.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)
        self.scenario_name = self._add_entry(form, 0, "场景名称")
        self.start_time = self._add_entry(form, 1, "开始时间")
        self.stop_time = self._add_entry(form, 2, "结束时间（24h）")
        self.stk_mode = self._add_combo(form, 3, "STK连接", [x[0] for x in STK_MODES])
        self.satellite_name = self._add_entry(form, 4, "目标卫星")

        ttk.Label(form, text="TLE文件").grid(row=5, column=0, sticky="w", pady=4)
        tle_row = ttk.Frame(form)
        tle_row.grid(row=5, column=1, sticky="ew", pady=4)
        self.tle_file = ttk.Entry(tle_row, width=34)
        self.tle_file.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(tle_row, text="浏览", command=self._browse_tle).pack(side=tk.LEFT, padx=6)

        self.ssc = self._add_entry(form, 6, "SSC编号")
        self.sat_step = self._add_entry(form, 7, "卫星传播步长/s")
        self.tx_power = self._add_entry(form, 8, "GPS发射功率/dBW")
        self.sensitivity = self._add_entry(form, 9, "接收灵敏度/dBW")
        self.analysis_step = self._add_entry(form, 10, "统计采样步长/s")

        self.run_button = ttk.Button(form, text="开始仿真", command=self.run_simulation)
        self.run_button.grid(row=11, column=0, columnspan=2, sticky="ew", pady=10)
        self.status = ttk.Label(form, text="状态：就绪", anchor="center")
        self.status.grid(row=12, column=0, columnspan=2)

    def _build_plot(self, parent):
        self.figure = Figure(figsize=(8, 5.5), facecolor="white")
        self.ax = self.figure.add_subplot(111)
        self._show_waiting()
        self.canvas = FigureCanvasTkAgg(self.figure, master=parent)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.save_button = ttk.Button(parent, text="保存图片", command=self.save_image, state=tk.DISABLED)
        self.save_button.pack(fill=tk.X, padx=8, pady=8)

    def _add_entry(self, parent, row, label):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=4)
        entry = ttk.Entry(parent, width=42)
        entry.grid(row=row, column=1, sticky="ew", pady=4)
        return entry

    def _add_combo(self, parent, row, label, values):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=4)
        combo = ttk.Combobox(parent, values=values, state="readonly", width=40)
        combo.grid(row=row, column=1, sticky="ew", pady=4)
        return combo

    def _set_status(self, text: str):
        self.status.config(text=text)
        self.win.update_idletasks()

    def _show_waiting(self):
        self.ax.clear()
        self.ax.set_title("等待仿真")
        self.ax.text(0.5, 0.5, "设置参数后点击“开始仿真”", ha="center", va="center", transform=self.ax.transAxes)
        self.ax.set_xticks([])
        self.ax.set_yticks([])

    def _browse_tle(self):
        path = filedialog.askopenfilename(
            title="选择目标卫星TLE",
            initialfile=self.tle_file.get(),
            filetypes=[("TLE文件", "*.txt *.tle"), ("全部文件", "*.*")],
        )
        if path:
            self.tle_file.delete(0, tk.END)
            self.tle_file.insert(0, path)

    def _write_cfg(self, cfg):
        pairs = [
            (self.scenario_name, cfg.scenario.name),
            (self.start_time, cfg.scenario.start_time),
            (self.stop_time, cfg.scenario.stop_time),
            (self.satellite_name, cfg.satellite.name),
            (self.tle_file, cfg.satellite.tle_file),
            (self.ssc, cfg.satellite.ssc),
            (self.sat_step, cfg.satellite.step),
            (self.tx_power, cfg.gps.tx_power),
            (self.sensitivity, cfg.receiver.sensitivity),
            (self.analysis_step, cfg.analysis.step),
        ]
        for widget, value in pairs:
            widget.delete(0, tk.END)
            widget.insert(0, str(value))
        self.stk_mode.set(next(k for k, v in STK_MODES if v == cfg.stk.mode))

    def _read_cfg(self):
        cfg = config_gps_visibility()
        cfg.scenario.name = self.scenario_name.get()
        cfg.scenario.start_time = self.start_time.get()
        cfg.scenario.stop_time = self.stop_time.get()
        cfg.stk.mode = _combo_value(self.stk_mode, STK_MODES)
        cfg.satellite.name = self.satellite_name.get()
        cfg.satellite.tle_file = self.tle_file.get()
        cfg.satellite.ssc = int(float(self.ssc.get()))
        cfg.satellite.step = float(self.sat_step.get())
        cfg.gps.tx_power = float(self.tx_power.get())
        cfg.receiver.sensitivity = float(self.sensitivity.get())
        cfg.analysis.step = float(self.analysis_step.get())
        return cfg

    def run_simulation(self):
        self.run_button.config(state=tk.DISABLED)
        self.save_button.config(state=tk.DISABLED)
        try:
            run_cfg = self._read_cfg()
            self._set_status("状态：正在连接STK...")
            if self.root_stk is None:
                _, self.root_stk = STKCore.start_stk(run_cfg.stk.mode)
            self._set_status("状态：正在加载GPS并计算...")
            self.last_result = run_gps_visibility(self.root_stk, run_cfg, self.ax)
            self.canvas.draw()
            self.save_button.config(state=tk.NORMAL)
            self._set_status(f"状态：完成，图片已保存到 {self.last_result.output.image_path}")
        except Exception as exc:
            self._set_status("状态：仿真失败")
            messagebox.showerror("仿真错误", str(exc))
        self.run_button.config(state=tk.NORMAL)

    def save_image(self):
        if self.last_result is None:
            messagebox.showinfo("保存图片", "请先完成仿真。")
            return
        default = self.last_result.output.result_dir / self.last_result.output.image_name
        path = filedialog.asksaveasfilename(
            title="选择保存目录和文件名",
            defaultextension=".png",
            initialfile=default.name,
            initialdir=str(default.parent),
            filetypes=[("PNG图片", "*.png")],
        )
        if not path:
            return
        self.figure.savefig(path, dpi=300, bbox_inches="tight", facecolor="white")
        self._set_status(f"状态：图片已保存到 {path}")

    def run(self):
        self.win.mainloop()


if __name__ == "__main__":
    GpsVisibilityApp().run()
