"""地面站新增与编辑窗口。"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from app.ui import entry_row, set_entry
from simulations.global_coverage.templates import StationConfig


class StationDialog:
    def __init__(self, parent, title: str, station: StationConfig):
        self.result: StationConfig | None = None
        self.window = tk.Toplevel(parent)
        self.window.title(title)
        self.window.resizable(False, False)
        self.window.transient(parent.winfo_toplevel())

        form = ttk.Frame(self.window, padding=14)
        form.pack(fill=tk.BOTH, expand=True)
        self.name_field = entry_row(form, 0, "地面站名称")
        self.lat_field = entry_row(form, 1, "纬度 / °")
        self.lon_field = entry_row(form, 2, "经度 / °")
        self.alt_field = entry_row(form, 3, "高度 / km")
        self.elevation_field = entry_row(form, 4, "最低仰角 / °")
        for field, value in (
            (self.name_field, station.name),
            (self.lat_field, station.lat),
            (self.lon_field, station.lon),
            (self.alt_field, station.alt),
            (self.elevation_field, station.min_elevation),
        ):
            set_entry(field, value)

        buttons = ttk.Frame(form)
        buttons.grid(row=5, column=0, columnspan=2, sticky=tk.E, pady=(10, 0))
        ttk.Button(buttons, text="取消", command=self.window.destroy).pack(
            side=tk.RIGHT
        )
        ttk.Button(buttons, text="确定", command=self._accept).pack(
            side=tk.RIGHT, padx=(0, 6)
        )
        self.window.bind("<Return>", lambda _event: self._accept())
        self.window.bind("<Escape>", lambda _event: self.window.destroy())

    @classmethod
    def show(cls, parent, title: str, station: StationConfig):
        dialog = cls(parent, title, station)
        dialog.window.grab_set()
        dialog.name_field.focus_set()
        dialog.name_field.select_range(0, tk.END)
        parent.wait_window(dialog.window)
        return dialog.result

    def _accept(self) -> None:
        try:
            station = StationConfig(
                name=self.name_field.get().strip(),
                lat=float(self.lat_field.get()),
                lon=float(self.lon_field.get()),
                alt=float(self.alt_field.get()),
                min_elevation=float(self.elevation_field.get()),
            )
            if not station.name:
                raise ValueError("地面站名称不能为空。")
            if not -90.0 <= station.lat <= 90.0:
                raise ValueError("纬度必须在 -90° 到 90° 之间。")
            if not -180.0 <= station.lon <= 180.0:
                raise ValueError("经度必须在 -180° 到 180° 之间。")
            if not 0.0 <= station.min_elevation <= 90.0:
                raise ValueError("最低仰角必须在 0° 到 90° 之间。")
        except ValueError as error:
            messagebox.showerror("参数错误", str(error), parent=self.window)
            return
        self.result = station
        self.window.destroy()
