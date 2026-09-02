"""全球通信时长 GUI 参数面板。"""

from __future__ import annotations

import copy
import tkinter as tk
from tkinter import ttk

from simulations.global_coverage.config import GlobalCoverageConfig
from simulations.global_coverage.templates import (
    StationConfig,
    satellite_template,
    station_template,
)


STK_MODES = (("新建STK", "new"), ("连接已运行STK", "running"))
SATELLITE_MODES = (("单星", "single"), ("多星", "multi"))
STATION_MODES = (
    ("单站", "single"),
    ("双站", "two"),
    ("三站", "three"),
    ("四站", "four"),
)


class GlobalCoveragePanel(ttk.Frame):
    def __init__(self, parent, config: GlobalCoverageConfig):
        super().__init__(parent, padding=12)
        self.pack(fill=tk.BOTH, expand=True)
        self._config = copy.deepcopy(config)
        self._status_variable = tk.StringVar(value="状态：就绪")

        self.scenario_field = self._add_entry(0, "场景名称")
        self.start_field = self._add_entry(1, "开始时间")
        self.stop_field = self._add_entry(2, "结束时间")
        self.stk_mode_field = self._add_combobox(
            3, "STK连接", [item[0] for item in STK_MODES]
        )
        self.satellite_field = self._add_combobox(
            4, "卫星方案", [item[0] for item in SATELLITE_MODES]
        )

        self.satellite_summary = ttk.Label(self, text="")
        self.satellite_summary.grid(
            row=5, column=0, columnspan=2, sticky="w", pady=4
        )
        self.station_mode_field = self._add_combobox(
            6, "地面站方案", [item[0] for item in STATION_MODES]
        )

        columns = (
            "enabled",
            "name",
            "latitude",
            "longitude",
            "altitude",
            "min_elevation",
        )
        headings = ("启用", "地面站", "纬度/°", "经度/°", "高度/km", "最低仰角/°")
        widths = (48, 88, 78, 82, 68, 90)
        self.station_table = ttk.Treeview(
            self, columns=columns, show="headings", height=7
        )
        for column, heading, width in zip(columns, headings, widths):
            self.station_table.heading(column, text=heading)
            self.station_table.column(column, width=width, anchor=tk.CENTER)
        self.station_table.grid(
            row=7, column=0, columnspan=2, sticky="nsew", pady=6
        )
        self.station_table.bind("<Double-1>", self._edit_station_cell)

        self.resolution_field = self._add_entry(8, "Coverage分辨率/°")
        self.min_elevation_field = self._add_entry(9, "网格最低仰角/°")

        self.run_button = ttk.Button(self, text="开始仿真")
        self.run_button.grid(
            row=10, column=0, columnspan=2, sticky="ew", pady=(8, 4)
        )
        self.run_all_button = ttk.Button(
            self, text="自动仿真全部(1×1~3×4)"
        )
        self.run_all_button.grid(
            row=11, column=0, columnspan=2, sticky="ew", pady=4
        )
        self.status_label = ttk.Label(
            self, textvariable=self._status_variable, anchor=tk.CENTER
        )
        self.status_label.grid(row=12, column=0, columnspan=2, sticky="ew", pady=8)

        self.columnconfigure(1, weight=1)
        self.rowconfigure(7, weight=1)
        self.satellite_field.bind(
            "<<ComboboxSelected>>", lambda _event: self._update_satellite_summary()
        )
        self.station_mode_field.bind(
            "<<ComboboxSelected>>", lambda _event: self._apply_station_mode()
        )
        self.write_config(config)

    def read_config(self) -> GlobalCoverageConfig:
        config = copy.deepcopy(self._config)
        config.scenario.name = self.scenario_field.get()
        config.scenario.start_time = self.start_field.get()
        config.scenario.stop_time = self.stop_field.get()
        config.stk.mode = _selected_value(self.stk_mode_field, STK_MODES)
        config.satellite_group.mode = _selected_value(
            self.satellite_field, SATELLITE_MODES
        )
        config.stations = self._read_stations()
        config.coverage.resolution = float(self.resolution_field.get())
        config.coverage.min_elevation = float(self.min_elevation_field.get())
        if not 0.1 <= config.coverage.resolution <= 10.0:
            raise ValueError("Coverage分辨率必须在 0.1° 到 10° 之间。")
        if not 0.0 <= config.coverage.min_elevation <= 90.0:
            raise ValueError("网格最低仰角必须在 0° 到 90° 之间。")
        return config

    def write_config(self, config: GlobalCoverageConfig) -> None:
        self._config = copy.deepcopy(config)
        _set_entry(self.scenario_field, config.scenario.name)
        _set_entry(self.start_field, config.scenario.start_time)
        _set_entry(self.stop_field, config.scenario.stop_time)
        self.stk_mode_field.set(_label_for_value(STK_MODES, config.stk.mode))
        self.satellite_field.set(
            _label_for_value(SATELLITE_MODES, config.satellite_group.mode)
        )
        station_index = min(max(len(config.stations), 1), 4) - 1
        self.station_mode_field.set(STATION_MODES[station_index][0])
        self._fill_station_table(config.stations)
        _set_entry(self.resolution_field, config.coverage.resolution)
        _set_entry(self.min_elevation_field, config.coverage.min_elevation)
        self._update_satellite_summary()

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

    def _apply_station_mode(self) -> None:
        mode = _selected_value(self.station_mode_field, STATION_MODES)
        self._fill_station_table(station_template(mode))

    def _update_satellite_summary(self) -> None:
        mode = _selected_value(self.satellite_field, SATELLITE_MODES)
        names = "、".join(config.name for config in satellite_template(mode))
        self.satellite_summary.configure(text=f"当前卫星：{names}")

    def _fill_station_table(self, stations: list[StationConfig]) -> None:
        for row in self.station_table.get_children():
            self.station_table.delete(row)
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
        stations: list[StationConfig] = []
        for row in self.station_table.get_children():
            enabled, name, latitude, longitude, altitude, min_elevation = (
                self.station_table.item(row, "values")
            )
            stations.append(
                StationConfig(
                    name=str(name),
                    lat=float(latitude),
                    lon=float(longitude),
                    alt=float(altitude),
                    min_elevation=float(min_elevation),
                    enabled=str(enabled).lower() in {"是", "true", "1"},
                )
            )
        return stations

    def _edit_station_cell(self, event) -> None:
        if self.station_table.identify_region(event.x, event.y) != "cell":
            return
        row_id = self.station_table.identify_row(event.y)
        column_id = self.station_table.identify_column(event.x)
        if not row_id or not column_id:
            return
        column_index = int(column_id[1:]) - 1

        values = list(self.station_table.item(row_id, "values"))
        if column_index == 0:
            values[0] = "否" if values[0] == "是" else "是"
            self.station_table.item(row_id, values=values)
            return

        bounds = self.station_table.bbox(row_id, column_id)
        if not bounds:
            return
        x_value, y_value, width, height = bounds
        editor = ttk.Entry(self.station_table)
        editor.place(x=x_value, y=y_value, width=width, height=height)
        editor.insert(0, values[column_index])
        editor.focus_set()

        committed = False

        def commit(_event=None) -> None:
            nonlocal committed
            if committed:
                return
            committed = True
            current_values = list(self.station_table.item(row_id, "values"))
            current_values[column_index] = editor.get()
            self.station_table.item(row_id, values=current_values)
            editor.destroy()

        editor.bind("<Return>", commit)
        editor.bind("<FocusOut>", commit)


def _selected_value(
    combobox: ttk.Combobox, items: tuple[tuple[str, str], ...]
) -> str:
    selected_label = combobox.get()
    for label, value in items:
        if label == selected_label:
            return value
    return items[0][1]


def _label_for_value(items: tuple[tuple[str, str], ...], selected: str) -> str:
    for label, value in items:
        if value == selected:
            return label
    return items[0][0]


def _set_entry(entry: ttk.Entry, value) -> None:
    entry.delete(0, tk.END)
    entry.insert(0, str(value))
