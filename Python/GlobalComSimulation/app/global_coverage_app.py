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

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from setup_project import setup_project
from simulations.global_coverage.config import config_global_coverage
from simulations.global_coverage.run_global_coverage import run_global_coverage
from simulations.global_coverage.templates import satellite_template, station_template
from stk_api.core import STKCore


STK_MODES = [("新建STK", "new"), ("连接已运行STK", "running")]
SAT_MODES = [("单星", "single"), ("多星", "multi")]
STATION_MODES = [("单站", "single"), ("双站", "two"), ("三站", "three"), ("四站", "four")]


def _combo_value(combo: ttk.Combobox, items: list[tuple[str, str]]) -> str:
    label = combo.get()
    for text, value in items:
        if text == label:
            return value
    return items[0][1]


class GlobalCoverageApp:
    def __init__(self):
        setup_project(ROOT)
        self.cfg = config_global_coverage()
        self.root_stk = None
        self.last_result = None

        self.win = tk.Tk()
        self.win.title("全球通信时长仿真")
        self.win.geometry("1500x800")

        left = ttk.LabelFrame(self.win, text="全球通信时长参数")
        left.pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=10)
        right = ttk.LabelFrame(self.win, text="全球通信时长梯度图")
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=10, pady=10)

        self._build_panel(left)
        self._build_plot(right)
        self._write_cfg(self.cfg)

    def _build_panel(self, parent):
        form = ttk.Frame(parent)
        form.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        self.scenario_name = self._add_entry(form, 0, "场景名称")
        self.start_time = self._add_entry(form, 1, "开始时间")
        self.stop_time = self._add_entry(form, 2, "结束时间")
        self.stk_mode = self._add_combo(form, 3, "STK连接", [x[0] for x in STK_MODES])
        self.sat_mode = self._add_combo(form, 4, "卫星方案", [x[0] for x in SAT_MODES])
        self.sat_summary = ttk.Label(form, text="")
        self.sat_summary.grid(row=5, column=0, columnspan=2, sticky="w", pady=4)
        self.station_mode = self._add_combo(form, 6, "地面站方案", [x[0] for x in STATION_MODES])

        cols = ("启用", "地面站", "纬度/°", "经度/°", "高度/km", "最低仰角/°")
        self.station_table = ttk.Treeview(form, columns=cols, show="headings", height=6)
        for col, width in zip(cols, (50, 90, 90, 90, 80, 90)):
            self.station_table.heading(col, text=col)
            self.station_table.column(col, width=width, anchor="center")
        self.station_table.grid(row=7, column=0, columnspan=2, sticky="nsew", pady=6)
        self.station_table.bind("<Double-1>", self._edit_station_cell)

        self.resolution = self._add_entry(form, 8, "Coverage分辨率/°")
        self.min_elev = self._add_entry(form, 9, "网格最低仰角/°")

        self.run_button = ttk.Button(form, text="开始仿真", command=self.run_simulation)
        self.run_button.grid(row=10, column=0, columnspan=2, sticky="ew", pady=8)
        self.run_all_button = ttk.Button(
            form, text="自动仿真全部(1×1~3×4)", command=self.run_all_simulations
        )
        self.run_all_button.grid(row=11, column=0, columnspan=2, sticky="ew")
        self.status = ttk.Label(form, text="状态：就绪", anchor="center")
        self.status.grid(row=12, column=0, columnspan=2, pady=8)

        self.sat_mode.bind("<<ComboboxSelected>>", lambda _e: self._update_sat_summary())
        self.station_mode.bind("<<ComboboxSelected>>", lambda _e: self._apply_station_mode())

    def _build_plot(self, parent):
        self.figure = Figure(figsize=(8, 6), facecolor="white")
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

    def _apply_station_mode(self):
        mode = _combo_value(self.station_mode, STATION_MODES)
        self._fill_station_table(station_template(mode))

    def _update_sat_summary(self):
        mode = _combo_value(self.sat_mode, SAT_MODES)
        names = "、".join(s["name"] for s in satellite_template(mode))
        self.sat_summary.config(text=f"当前卫星：{names}")

    def _fill_station_table(self, stations: list[dict]):
        for item in self.station_table.get_children():
            self.station_table.delete(item)
        for station in stations:
            self.station_table.insert(
                "",
                tk.END,
                values=(
                    "是" if station["enabled"] else "否",
                    station["name"],
                    f"{station['lat']:.6f}",
                    f"{station['lon']:.6f}",
                    station["alt"],
                    station["min_elevation"],
                ),
            )

    def _read_stations(self) -> list[dict]:
        stations = []
        for item in self.station_table.get_children():
            enabled, name, lat, lon, alt, min_el = self.station_table.item(item, "values")
            stations.append(
                {
                    "enabled": str(enabled) in {"是", "True", "1", "true"},
                    "name": str(name),
                    "lat": float(lat),
                    "lon": float(lon),
                    "alt": float(alt),
                    "min_elevation": float(min_el),
                }
            )
        return stations

    def _edit_station_cell(self, event):
        region = self.station_table.identify("region", event.x, event.y)
        if region != "cell":
            return
        row_id = self.station_table.identify_row(event.y)
        col = self.station_table.identify_column(event.x)
        col_index = int(col.replace("#", "")) - 1
        bbox = self.station_table.bbox(row_id, col)
        if not bbox:
            return
        x, y, w, h = bbox
        value = self.station_table.item(row_id, "values")[col_index]
        editor = ttk.Entry(self.station_table)
        editor.place(x=x, y=y, width=w, height=h)
        editor.insert(0, value)
        editor.focus()

        def commit(_event=None):
            values = list(self.station_table.item(row_id, "values"))
            values[col_index] = editor.get()
            self.station_table.item(row_id, values=values)
            editor.destroy()

        editor.bind("<Return>", commit)
        editor.bind("<FocusOut>", commit)

    def _write_cfg(self, cfg):
        self.scenario_name.delete(0, tk.END)
        self.scenario_name.insert(0, cfg.scenario.name)
        self.start_time.delete(0, tk.END)
        self.start_time.insert(0, cfg.scenario.start_time)
        self.stop_time.delete(0, tk.END)
        self.stop_time.insert(0, cfg.scenario.stop_time)
        self.stk_mode.set(next(k for k, v in STK_MODES if v == cfg.stk.mode))
        self.sat_mode.set(next(k for k, v in SAT_MODES if v == cfg.satellite_group.mode))
        count = min(max(len(cfg.stations), 1), 4)
        self.station_mode.set(STATION_MODES[count - 1][0])
        self._fill_station_table(cfg.stations)
        self.resolution.delete(0, tk.END)
        self.resolution.insert(0, str(cfg.coverage.resolution))
        self.min_elev.delete(0, tk.END)
        self.min_elev.insert(0, str(cfg.coverage.min_elevation))
        self._update_sat_summary()

    def _read_cfg(self):
        cfg = config_global_coverage()
        cfg.scenario.name = self.scenario_name.get()
        cfg.scenario.start_time = self.start_time.get()
        cfg.scenario.stop_time = self.stop_time.get()
        cfg.stk.mode = _combo_value(self.stk_mode, STK_MODES)
        cfg.satellite_group.mode = _combo_value(self.sat_mode, SAT_MODES)
        cfg.stations = self._read_stations()
        cfg.coverage.resolution = float(self.resolution.get())
        cfg.coverage.min_elevation = float(self.min_elev.get())
        return cfg

    def _ensure_stk(self, mode: str):
        if self.root_stk is None:
            _, self.root_stk = STKCore.start_stk(mode)

    def run_simulation(self):
        self.run_button.config(state=tk.DISABLED)
        self.save_button.config(state=tk.DISABLED)
        try:
            run_cfg = self._read_cfg()
            self._set_status("状态：正在连接STK...")
            self._ensure_stk(run_cfg.stk.mode)
            self._set_status("状态：正在仿真...")
            self.last_result = run_global_coverage(self.root_stk, run_cfg, self.ax)
            self.canvas.draw()
            self.save_button.config(state=tk.NORMAL)
            self._set_status(f"状态：完成，图片已保存到 {self.last_result.output.image_path}")
        except Exception as exc:
            self._set_status("状态：仿真失败")
            messagebox.showerror("仿真错误", str(exc))
        self.run_button.config(state=tk.NORMAL)

    def run_all_simulations(self):
        self.run_button.config(state=tk.DISABLED)
        self.run_all_button.config(state=tk.DISABLED)
        self.save_button.config(state=tk.DISABLED)
        sat_modes = ["single", "multi"]
        st_modes = ["single", "two", "three", "four"]
        sat_labels = ["单星", "多星"]
        st_labels = ["单站", "双站", "三站", "四站"]
        total = len(sat_modes) * len(st_modes)
        idx = 0
        try:
            for si, sat_mode in enumerate(sat_modes):
                for sti, st_mode in enumerate(st_modes):
                    idx += 1
                    run_cfg = self._read_cfg()
                    run_cfg.satellite_group.mode = sat_mode
                    run_cfg.stations = station_template(st_mode)
                    self._set_status(
                        f"状态：自动仿真 {idx}/{total} ({sat_labels[si]}{st_labels[sti]})..."
                    )
                    self._ensure_stk(run_cfg.stk.mode)
                    self.last_result = run_global_coverage(self.root_stk, run_cfg, self.ax)
                    self.canvas.draw()
                    self._set_status(
                        f"状态：{idx}/{total} 完成，图片 {self.last_result.output.image_path}"
                    )
                    self.win.update()
                    time.sleep(5)
                    if self.root_stk is not None and self.root_stk.CurrentScenario is not None:
                        self.root_stk.CloseScenario()
            self.save_button.config(state=tk.NORMAL)
            self._set_status(
                f"状态：全部 {total} 组完成，图片保存到 {self.last_result.output.result_dir}"
            )
        except Exception as exc:
            self._set_status("状态：自动仿真失败")
            messagebox.showerror("仿真错误", str(exc))
        self.run_button.config(state=tk.NORMAL)
        self.run_all_button.config(state=tk.NORMAL)

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
    GlobalCoverageApp().run()
