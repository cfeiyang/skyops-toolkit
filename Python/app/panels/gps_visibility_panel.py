"""GPS 可见数量 GUI 参数面板。"""

from __future__ import annotations

import copy
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from app.ui import combo_row, entry_row, selected_value, set_entry
from simulations.gps_visibility.config import GPSVisibilityConfig


STK_MODES = (("新建 STK", "new"), ("连接已运行 STK", "running"))


class GPSVisibilityPanel(ttk.Frame):
    def __init__(self, parent, config: GPSVisibilityConfig):
        super().__init__(parent, padding=10)
        self.pack(fill=tk.BOTH, expand=True)
        self._config = copy.deepcopy(config)
        self._status = tk.StringVar(value="就绪")

        notebook = ttk.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True)
        scenario_tab = ttk.Frame(notebook, padding=12)
        link_tab = ttk.Frame(notebook, padding=12)
        notebook.add(scenario_tab, text="场景与卫星")
        notebook.add(link_tab, text="链路与采样")
        self._build_scenario_tab(scenario_tab)
        self._build_link_tab(link_tab)

        self.run_button = ttk.Button(
            self, text="开始仿真", style="Primary.TButton"
        )
        self.run_button.pack(fill=tk.X, pady=(10, 0))
        ttk.Label(self, textvariable=self._status, style="Status.TLabel").pack(
            fill=tk.X, pady=(6, 0)
        )
        self.write_config(config)

    def _build_scenario_tab(self, parent) -> None:
        group = ttk.LabelFrame(parent, text="场景")
        group.pack(fill=tk.X, pady=(0, 10))
        self.scenario_field = entry_row(group, 0, "场景名称")
        self.start_field = entry_row(group, 1, "开始时间")
        self.stop_field = entry_row(group, 2, "结束时间")
        self.stk_mode_field = combo_row(
            group, 3, "STK 连接", [label for label, _ in STK_MODES]
        )

        satellite_group = ttk.LabelFrame(parent, text="目标卫星")
        satellite_group.pack(fill=tk.X)
        self.satellite_name_field = entry_row(satellite_group, 0, "卫星名称")
        self.ssc_field = entry_row(satellite_group, 1, "SSC 编号")
        self.satellite_step_field = entry_row(
            satellite_group, 2, "传播步长 / s"
        )
        ttk.Label(satellite_group, text="TLE 文件").grid(
            row=3, column=0, sticky=tk.W, padx=10, pady=7
        )
        file_row = ttk.Frame(satellite_group)
        file_row.grid(row=3, column=1, sticky=tk.EW, padx=(0, 10), pady=7)
        self.tle_field = ttk.Entry(file_row)
        self.tle_field.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(file_row, text="浏览", command=self._browse_tle).pack(
            side=tk.LEFT, padx=(6, 0)
        )
        satellite_group.columnconfigure(1, weight=1)

    def _build_link_tab(self, parent) -> None:
        link_group = ttk.LabelFrame(parent, text="GPS 链路")
        link_group.pack(fill=tk.X, pady=(0, 10))
        self.tx_power_field = entry_row(link_group, 0, "发射功率 / dBW")
        self.sensitivity_field = entry_row(link_group, 1, "接收灵敏度 / dBW")

        analysis_group = ttk.LabelFrame(parent, text="统计")
        analysis_group.pack(fill=tk.X)
        self.analysis_step_field = entry_row(
            analysis_group, 0, "采样步长 / s"
        )

    def read_config(self) -> GPSVisibilityConfig:
        config = copy.deepcopy(self._config)
        config.scenario.name = self.scenario_field.get().strip()
        config.scenario.start_time = self.start_field.get().strip()
        config.scenario.stop_time = self.stop_field.get().strip()
        config.stk.mode = selected_value(self.stk_mode_field, STK_MODES)
        config.satellite.name = self.satellite_name_field.get().strip()
        config.satellite.tle_file = Path(self.tle_field.get().strip())
        config.satellite.ssc = int(float(self.ssc_field.get()))
        config.satellite.step = float(self.satellite_step_field.get())
        config.gps.tx_power = float(self.tx_power_field.get())
        config.receiver.sensitivity = float(self.sensitivity_field.get())
        config.analysis.step = float(self.analysis_step_field.get())
        if not config.scenario.name or not config.satellite.name:
            raise ValueError("场景名称和卫星名称不能为空。")
        if config.satellite.ssc < 1:
            raise ValueError("SSC 编号必须大于或等于 1。")
        if config.satellite.step < 1 or config.analysis.step < 1:
            raise ValueError("传播和统计采样步长必须大于或等于 1 秒。")
        if not config.satellite.tle_file.is_file():
            raise ValueError(f"TLE 文件不存在：{config.satellite.tle_file}")
        return config

    def write_config(self, config: GPSVisibilityConfig) -> None:
        self._config = copy.deepcopy(config)
        for field, value in (
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
        ):
            set_entry(field, value)
        self.stk_mode_field.set(
            next(label for label, value in STK_MODES if value == config.stk.mode)
        )

    def set_status(self, text: str) -> None:
        self._status.set(text.removeprefix("状态："))

    def set_busy(self, busy: bool) -> None:
        self.run_button.configure(state=tk.DISABLED if busy else tk.NORMAL)

    def _browse_tle(self) -> None:
        current = Path(self.tle_field.get())
        selected = filedialog.askopenfilename(
            title="选择目标卫星 TLE",
            initialdir=str(current.parent),
            initialfile=current.name,
            filetypes=[("TLE 文件", "*.txt *.tle"), ("全部文件", "*.*")],
        )
        if selected:
            set_entry(self.tle_field, selected)
