"""全球通信时长 GUI 参数面板。"""

from __future__ import annotations

import copy
import tkinter as tk
from tkinter import messagebox, ttk

from app.station_dialog import StationDialog
from app.ui import combo_row, entry_row, label_for_value, selected_value, set_entry
from simulations.global_coverage.config import GlobalCoverageConfig
from simulations.global_coverage.templates import (
    StationConfig,
    satellite_template,
    station_template,
)


STK_MODES = (("新建 STK", "new"), ("连接已运行 STK", "running"))
SATELLITE_MODES = (("单星", "single"), ("多星", "multi"))
STATION_PRESETS = (
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
            action_bar, text="运行预设 8 组", style="Secondary.TButton"
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
        self.satellite_field.bind(
            "<<ComboboxSelected>>", lambda _event: self._update_satellite_summary()
        )

        coverage_group = ttk.LabelFrame(parent, text="覆盖分析")
        coverage_group.pack(fill=tk.X)
        self.resolution_field = entry_row(
            coverage_group, 0, "网格分辨率 / °"
        )
        self.min_elevation_field = entry_row(
            coverage_group, 1, "网格最低仰角 / °"
        )

    def _build_station_tab(self, parent) -> None:
        preset_bar = ttk.Frame(parent)
        preset_bar.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(preset_bar, text="快速载入预设").pack(side=tk.LEFT)
        self.station_preset_field = ttk.Combobox(
            preset_bar,
            values=[label for label, _ in STATION_PRESETS],
            state="readonly",
            width=8,
        )
        self.station_preset_field.pack(side=tk.LEFT, padx=(8, 6))
        ttk.Button(
            preset_bar, text="载入", command=self._load_station_preset
        ).pack(side=tk.LEFT)

        action_bar = ttk.Frame(parent)
        action_bar.pack(fill=tk.X, pady=(0, 8))
        ttk.Button(
            action_bar, text="＋ 添加地面站", command=self._add_station
        ).pack(side=tk.LEFT)
        ttk.Button(
            action_bar, text="编辑选中", command=self._edit_selected_station
        ).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(
            action_bar, text="删除选中", command=self._delete_selected_stations
        ).pack(side=tk.LEFT, padx=(6, 0))

        table_host = ttk.Frame(parent)
        table_host.pack(fill=tk.BOTH, expand=True)
        columns = ("name", "lat", "lon", "alt", "elevation")
        headings = ("地面站", "纬度/°", "经度/°", "高度/km", "最低仰角/°")
        widths = (110, 82, 88, 74, 96)
        self.station_table = ttk.Treeview(
            table_host,
            columns=columns,
            show="headings",
            height=10,
            selectmode="extended",
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
        self.station_table.bind(
            "<Double-1>", lambda _event: self._edit_selected_station()
        )
        ttk.Label(
            parent,
            text="表格中的每个地面站都会参与仿真；双击一行可编辑参数。",
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
        preset_index = min(max(len(config.stations), 1), 4) - 1
        self.station_preset_field.set(STATION_PRESETS[preset_index][0])
        self._fill_station_table(config.stations)
        self._update_satellite_summary()

    def set_status(self, text: str) -> None:
        self._status.set(text.removeprefix("状态："))

    def set_busy(self, busy: bool) -> None:
        state = tk.DISABLED if busy else tk.NORMAL
        self.run_button.configure(state=state)
        self.run_all_button.configure(state=state)

    def _load_station_preset(self) -> None:
        mode = selected_value(self.station_preset_field, STATION_PRESETS)
        self._fill_station_table(station_template(mode))

    def _add_station(self) -> None:
        names = {
            self._station_from_row(row).name.casefold()
            for row in self.station_table.get_children()
        }
        number = 1
        while f"station{number}" in names:
            number += 1
        station = StationConfig(
            name=f"Station{number}",
            lat=0.0,
            lon=0.0,
            alt=0.0,
            min_elevation=15.0,
        )
        created = StationDialog.show(self, "添加地面站", station)
        if created is not None:
            if created.name.casefold() in names:
                messagebox.showerror(
                    "参数错误", "地面站名称不能重复。", parent=self
                )
                return
            row = self._insert_station(created)
            self.station_table.selection_set(row)
            self.station_table.see(row)

    def _edit_selected_station(self) -> None:
        selected = self.station_table.selection()
        if len(selected) != 1:
            messagebox.showinfo(
                "编辑地面站", "请先选择一个地面站。", parent=self
            )
            return
        row = selected[0]
        station = self._station_from_row(row)
        updated = StationDialog.show(self, "编辑地面站", station)
        if updated is not None:
            other_names = {
                self._station_from_row(other).name.casefold()
                for other in self.station_table.get_children()
                if other != row
            }
            if updated.name.casefold() in other_names:
                messagebox.showerror(
                    "参数错误", "地面站名称不能重复。", parent=self
                )
                return
            self.station_table.item(row, values=_station_values(updated))

    def _delete_selected_stations(self) -> None:
        selected = self.station_table.selection()
        if not selected:
            messagebox.showinfo(
                "删除地面站", "请先选择要删除的地面站。", parent=self
            )
            return
        self.station_table.delete(*selected)

    def _update_satellite_summary(self) -> None:
        mode = selected_value(self.satellite_field, SATELLITE_MODES)
        names = "、".join(item.name for item in satellite_template(mode))
        self.satellite_summary.configure(text=f"当前卫星：{names}")

    def _fill_station_table(self, stations: list[StationConfig]) -> None:
        self.station_table.delete(*self.station_table.get_children())
        for station in stations:
            self._insert_station(station)

    def _insert_station(self, station: StationConfig) -> str:
        return self.station_table.insert("", tk.END, values=_station_values(station))

    def _station_from_row(self, row: str) -> StationConfig:
        name, lat, lon, alt, elevation = self.station_table.item(row, "values")
        return StationConfig(
            name=str(name).strip(),
            lat=float(lat),
            lon=float(lon),
            alt=float(alt),
            min_elevation=float(elevation),
        )

    def _read_stations(self) -> list[StationConfig]:
        stations = [
            self._station_from_row(row) for row in self.station_table.get_children()
        ]
        if not stations:
            raise ValueError("请至少添加一个地面站。")
        names = [station.name.casefold() for station in stations]
        if len(names) != len(set(names)):
            raise ValueError("地面站名称不能重复。")
        return stations


def _station_values(station: StationConfig) -> tuple[str, str, str, str, str]:
    return (
        station.name,
        f"{station.lat:.8g}",
        f"{station.lon:.8g}",
        f"{station.alt:g}",
        f"{station.min_elevation:g}",
    )
