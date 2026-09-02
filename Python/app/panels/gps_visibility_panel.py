"""GPS 可见数量 GUI 参数面板。"""

from __future__ import annotations

import copy
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from simulations.gps_visibility.config import GPSVisibilityConfig


STK_MODES = (("新建STK", "new"), ("连接已运行STK", "running"))


class GPSVisibilityPanel(ttk.Frame):
    def __init__(self, parent, config: GPSVisibilityConfig):
        super().__init__(parent, padding=12)
        self.pack(fill=tk.BOTH, expand=True)
        self._config = copy.deepcopy(config)
        self._status_variable = tk.StringVar(value="状态：就绪")

        self.scenario_field = self._add_entry(0, "场景名称")
        self.start_field = self._add_entry(1, "开始时间")
        self.stop_field = self._add_entry(2, "结束时间（24h）")
        self.stk_mode_field = self._add_combobox(
            3, "STK连接", [item[0] for item in STK_MODES]
        )
        self.satellite_name_field = self._add_entry(4, "目标卫星")

        ttk.Label(self, text="TLE文件").grid(
            row=5, column=0, sticky="w", pady=4, padx=(0, 8)
        )
        tle_frame = ttk.Frame(self)
        tle_frame.grid(row=5, column=1, sticky="ew", pady=4)
        self.tle_field = ttk.Entry(tle_frame, width=34)
        self.tle_field.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(tle_frame, text="浏览", command=self._browse_tle).pack(
            side=tk.LEFT, padx=(6, 0)
        )

        self.ssc_field = self._add_entry(6, "SSC编号")
        self.satellite_step_field = self._add_entry(7, "卫星传播步长/s")
        self.tx_power_field = self._add_entry(8, "GPS发射功率/dBW")
        self.sensitivity_field = self._add_entry(9, "接收灵敏度/dBW")
        self.analysis_step_field = self._add_entry(10, "统计采样步长/s")

        self.run_button = ttk.Button(self, text="开始仿真")
        self.run_button.grid(
            row=11, column=0, columnspan=2, sticky="ew", pady=10
        )
        self.status_label = ttk.Label(
            self, textvariable=self._status_variable, anchor=tk.CENTER
        )
        self.status_label.grid(row=12, column=0, columnspan=2, sticky="ew")
        self.columnconfigure(1, weight=1)
        self.write_config(config)

    def read_config(self) -> GPSVisibilityConfig:
        config = copy.deepcopy(self._config)
        config.scenario.name = self.scenario_field.get()
        config.scenario.start_time = self.start_field.get()
        config.scenario.stop_time = self.stop_field.get()
        config.stk.mode = _selected_value(self.stk_mode_field)
        config.satellite.name = self.satellite_name_field.get()
        config.satellite.tle_file = Path(self.tle_field.get())
        config.satellite.ssc = int(float(self.ssc_field.get()))
        config.satellite.step = float(self.satellite_step_field.get())
        config.gps.tx_power = float(self.tx_power_field.get())
        config.receiver.sensitivity = float(self.sensitivity_field.get())
        config.analysis.step = float(self.analysis_step_field.get())
        if config.satellite.ssc < 1:
            raise ValueError("SSC编号必须大于或等于 1。")
        if config.satellite.step < 1:
            raise ValueError("卫星传播步长必须大于或等于 1 秒。")
        if config.analysis.step < 1:
            raise ValueError("统计采样步长必须大于或等于 1 秒。")
        return config

    def write_config(self, config: GPSVisibilityConfig) -> None:
        self._config = copy.deepcopy(config)
        pairs = (
            (self.scenario_field, config.scenario.name),
            (self.start_field, config.scenario.start_time),
            (self.stop_field, config.scenario.stop_time),
            (self.satellite_name_field, config.satellite.name),
            (self.tle_field, config.satellite.tle_file),
            (self.ssc_field, config.satellite.ssc),
            (self.satellite_step_field, config.satellite.step),
            (self.tx_power_field, config.gps.tx_power),
            (self.sensitivity_field, config.receiver.sensitivity),
            (self.analysis_step_field, config.analysis.step),
        )
        for entry, value in pairs:
            _set_entry(entry, value)
        self.stk_mode_field.set(
            next(label for label, value in STK_MODES if value == config.stk.mode)
        )

    def set_status(self, text: str) -> None:
        self._status_variable.set(text)
        self.update_idletasks()

    def _add_entry(self, row: int, label_text: str) -> ttk.Entry:
        ttk.Label(self, text=label_text).grid(
            row=row, column=0, sticky="w", pady=4, padx=(0, 8)
        )
        entry = ttk.Entry(self, width=42)
        entry.grid(row=row, column=1, sticky="ew", pady=4)
        return entry

    def _add_combobox(
        self, row: int, label_text: str, values: list[str]
    ) -> ttk.Combobox:
        ttk.Label(self, text=label_text).grid(
            row=row, column=0, sticky="w", pady=4, padx=(0, 8)
        )
        combobox = ttk.Combobox(
            self, values=values, state="readonly", width=40
        )
        combobox.grid(row=row, column=1, sticky="ew", pady=4)
        return combobox

    def _browse_tle(self) -> None:
        current_path = Path(self.tle_field.get())
        selected = filedialog.askopenfilename(
            title="选择目标卫星TLE",
            initialdir=str(current_path.parent),
            initialfile=current_path.name,
            filetypes=[("TLE文件", "*.txt *.tle"), ("全部文件", "*.*")],
        )
        if selected:
            _set_entry(self.tle_field, selected)


def _selected_value(combobox: ttk.Combobox) -> str:
    selected_label = combobox.get()
    for label, value in STK_MODES:
        if label == selected_label:
            return value
    return STK_MODES[0][1]


def _set_entry(entry: ttk.Entry, value) -> None:
    entry.delete(0, tk.END)
    entry.insert(0, str(value))
