"""全球通信时长 GUI 参数面板。"""

from __future__ import annotations

import copy
import tkinter as tk
from tkinter import ttk

from app.ui import combo_row, entry_row, label_for_value, selected_value, set_entry
from simulations.global_coverage.config import GlobalCoverageConfig
from simulations.global_coverage.templates import (
    StationConfig,
    satellite_template,
    station_template,
)


STK_MODES = (("新建 STK", "new"), ("连接已运行 STK", "running"))
SATELLITE_MODES = (("单星", "single"), ("多星", "multi"))
STATION_MODES = (
    ("单站", "single"),
    ("双站", "two"),
    ("三站", "three"),
    ("四站", "four"),
)


class GlobalCoveragePanel(ttk.Frame):
    def __init__(self, parent, config: GlobalCoverageConfig):
        super().__init__(parent, padding=10)
        self.pack(fill=tk.BOTH, expand=True)
        self._config = copy.deepcopy(config)
        self._status = tk.StringVar(value="就绪")

        notebook = ttk.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True)
        general_tab = ttk.Frame(notebook, padding=12)
        station_tab = ttk.Frame(notebook, padding=10)
        notebook.add(general_tab, text="仿真设置")
        notebook.add(station_tab, text="地面站")
        self._build_general_tab(general_tab)
        self._build_station_tab(station_tab)

        action_bar = ttk.Frame(self)
        action_bar.pack(fill=tk.X, pady=(10, 0))
        self.run_button = ttk.Button(
            action_bar, text="开始仿真", style="Primary.TButton"
        )
        self.run_button.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.run_all_button = ttk.Button(
            action_bar, text="运行全部 8 组", style="Secondary.TButton"
        )
        self.run_all_button.pack(side=tk.LEFT, padx=(8, 0))
        ttk.Label(self, textvariable=self._status, style="Status.TLabel").pack(
            fill=tk.X, pady=(6, 0)
        )
        self.write_config(config)

    def _build_general_tab(self, parent) -> None:
        scenario_group = ttk.LabelFrame(parent, text="场景")
        scenario_group.pack(fill=tk.X, pady=(0, 10))
        self.scenario_field = entry_row(scenario_group, 0, "场景名称")
        self.start_field = entry_row(scenario_group, 1, "开始时间")
        self.stop_field = entry_row(scenario_group, 2, "结束时间")

        model_group = ttk.LabelFrame(parent, text="模型")
        model_group.pack(fill=tk.X, pady=(0, 10))
        self.stk_mode_field = combo_row(
            model_group, 0, "STK 连接", [label for label, _ in STK_MODES]
        )
        self.satellite_field = combo_row(
            model_group, 1, "卫星方案", [label for label, _ in SATELLITE_MODES]
        )
        self.satellite_summary = ttk.Label(model_group, foreground="#556070")
        self.satellite_summary.grid(
            row=2, column=0, columnspan=2, sticky=tk.W, padx=10, pady=(2, 8)
        )

        coverage_group = ttk.LabelFrame(parent, text="覆盖分析")
        coverage_group.pack(fill=tk.X)
        self.resolution_field = entry_row(
            coverage_group, 0, "网格分辨率 / °"
        )
        self.min_elevation_field = entry_row(
            coverage_group, 1, "最低仰角 / °"
        )
        self.satellite_field.bind(
            "<<ComboboxSelected>>", lambda _event: self._update_satellite_summary()
        )

    def _build_station_tab(self, parent) -> None:
        header = ttk.Frame(parent)
        header.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(header, text="地面站方案").pack(side=tk.LEFT)
        self.station_mode_field = ttk.Combobox(
            header,
            values=[label for label, _ in STATION_MODES],
            state="readonly",
            width=12,
        )
        self.station_mode_field.pack(side=tk.LEFT, padx=(10, 0))
        self.station_mode_field.bind(
            "<<ComboboxSelected>>", lambda _event: self._apply_station_mode()
        )

        table_host = ttk.Frame(parent)
        table_host.pack(fill=tk.BOTH, expand=True)
        columns = ("enabled", "name", "lat", "lon", "alt", "elevation")
        headings = ("启用", "地面站", "纬度/°", "经度/°", "高度/km", "最低仰角/°")
        widths = (50, 100, 82, 88, 74, 96)
        self.station_table = ttk.Treeview(
            table_host, columns=columns, show="headings", height=10
        )
        for column, heading, width in zip(columns, headings, widths):
            self.station_table.heading(column, text=heading)
            self.station_table.column(
                column,
                width=width,
                minwidth=width,
                anchor=tk.CENTER,
                stretch=column == "name",
            )
        y_scroll = ttk.Scrollbar(
            table_host, orient=tk.VERTICAL, command=self.station_table.yview
        )
        x_scroll = ttk.Scrollbar(
            table_host, orient=tk.HORIZONTAL, command=self.station_table.xview
        )
        self.station_table.configure(
            yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set
        )
        self.station_table.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        table_host.rowconfigure(0, weight=1)
        table_host.columnconfigure(0, weight=1)
        self.station_table.bind("<Double-1>", self._edit_station_cell)
        ttk.Label(
            parent,
            text="提示：双击单元格可编辑；双击“启用”列可切换。",
            foreground="#6f7782",
        ).pack(anchor=tk.W, pady=(6, 0))

    def read_config(self) -> GlobalCoverageConfig:
        config = copy.deepcopy(self._config)
        config.scenario.name = self.scenario_field.get().strip()
        config.scenario.start_time = self.start_field.get().strip()
        config.scenario.stop_time = self.stop_field.get().strip()
        config.stk.mode = selected_value(self.stk_mode_field, STK_MODES)
        config.satellite_group.mode = selected_value(
            self.satellite_field, SATELLITE_MODES
        )
        config.stations = self._read_stations()
        config.coverage.resolution = float(self.resolution_field.get())
        config.coverage.min_elevation = float(self.min_elevation_field.get())
        if not config.scenario.name:
            raise ValueError("场景名称不能为空。")
        if not 0.1 <= config.coverage.resolution <= 10.0:
            raise ValueError("Coverage 分辨率必须在 0.1° 到 10° 之间。")
        if not 0.0 <= config.coverage.min_elevation <= 90.0:
            raise ValueError("网格最低仰角必须在 0° 到 90° 之间。")
        if not any(station.enabled for station in config.stations):
            raise ValueError("请至少启用一个地面站。")
        return config

    def write_config(self, config: GlobalCoverageConfig) -> None:
        self._config = copy.deepcopy(config)
        for field, value in (
            (self.scenario_field, config.scenario.name),
            (self.start_field, config.scenario.start_time),
            (self.stop_field, config.scenario.stop_time),
            (self.resolution_field, config.coverage.resolution),
            (self.min_elevation_field, config.coverage.min_elevation),
        ):
            set_entry(field, value)
        self.stk_mode_field.set(label_for_value(STK_MODES, config.stk.mode))
        self.satellite_field.set(
            label_for_value(SATELLITE_MODES, config.satellite_group.mode)
        )
        self.station_mode_field.set(STATION_MODES[min(len(config.stations), 4) - 1][0])
        self._fill_station_table(config.stations)
        self._update_satellite_summary()

    def set_status(self, text: str) -> None:
        self._status.set(text.removeprefix("状态："))

    def set_busy(self, busy: bool) -> None:
        state = tk.DISABLED if busy else tk.NORMAL
        self.run_button.configure(state=state)
        self.run_all_button.configure(state=state)

    def _apply_station_mode(self) -> None:
        mode = selected_value(self.station_mode_field, STATION_MODES)
        self._fill_station_table(station_template(mode))

    def _update_satellite_summary(self) -> None:
        mode = selected_value(self.satellite_field, SATELLITE_MODES)
        names = "、".join(item.name for item in satellite_template(mode))
        self.satellite_summary.configure(text=f"当前卫星：{names}")

    def _fill_station_table(self, stations: list[StationConfig]) -> None:
        self.station_table.delete(*self.station_table.get_children())
        for station in stations:
            self.station_table.insert(
                "",
                tk.END,
                values=(
                    "是" if station.enabled else "否",
                    station.name,
                    f"{station.lat:.8g}",
                    f"{station.lon:.8g}",
                    f"{station.alt:g}",
                    f"{station.min_elevation:g}",
                ),
            )

    def _read_stations(self) -> list[StationConfig]:
        stations = []
        for row in self.station_table.get_children():
            enabled, name, lat, lon, alt, elevation = self.station_table.item(
                row, "values"
            )
            station = StationConfig(
                name=str(name).strip(),
                lat=float(lat),
                lon=float(lon),
                alt=float(alt),
                min_elevation=float(elevation),
                enabled=str(enabled) == "是",
            )
            if not -90 <= station.lat <= 90 or not -180 <= station.lon <= 360:
                raise ValueError(f"地面站 {station.name} 的经纬度超出范围。")
            stations.append(station)
        return stations

    def _edit_station_cell(self, event) -> None:
        if self.station_table.identify_region(event.x, event.y) != "cell":
            return
        row = self.station_table.identify_row(event.y)
        column = self.station_table.identify_column(event.x)
        if not row or not column:
            return
        index = int(column[1:]) - 1
        values = list(self.station_table.item(row, "values"))
        if index == 0:
            values[0] = "否" if values[0] == "是" else "是"
            self.station_table.item(row, values=values)
            return

        bounds = self.station_table.bbox(row, column)
        if not bounds:
            return
        editor = ttk.Entry(self.station_table)
        editor.place(x=bounds[0], y=bounds[1], width=bounds[2], height=bounds[3])
        editor.insert(0, values[index])
        editor.select_range(0, tk.END)
        editor.focus_set()

        def commit(_event=None) -> None:
            if not editor.winfo_exists():
                return
            current = list(self.station_table.item(row, "values"))
            current[index] = editor.get()
            self.station_table.item(row, values=current)
            editor.destroy()

        editor.bind("<Return>", commit)
        editor.bind("<FocusOut>", commit)
        editor.bind("<Escape>", lambda _event: editor.destroy())
