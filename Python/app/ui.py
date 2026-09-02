"""Tkinter 与 Matplotlib 的公共界面组件。"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure

from utils.plotting import configure_chinese_font


def entry_row(parent, row: int, label: str) -> ttk.Entry:
    ttk.Label(parent, text=label).grid(
        row=row, column=0, sticky=tk.W, padx=10, pady=7
    )
    entry = ttk.Entry(parent)
    entry.grid(row=row, column=1, sticky=tk.EW, padx=(0, 10), pady=7)
    parent.columnconfigure(1, weight=1)
    return entry


def combo_row(parent, row: int, label: str, values) -> ttk.Combobox:
    ttk.Label(parent, text=label).grid(
        row=row, column=0, sticky=tk.W, padx=10, pady=7
    )
    combo = ttk.Combobox(parent, values=values, state="readonly")
    combo.grid(row=row, column=1, sticky=tk.EW, padx=(0, 10), pady=7)
    parent.columnconfigure(1, weight=1)
    return combo


def set_entry(entry: ttk.Entry, value) -> None:
    entry.delete(0, tk.END)
    entry.insert(0, str(value))


def selected_value(combo: ttk.Combobox, items) -> str:
    return next((value for label, value in items if label == combo.get()), items[0][1])


def label_for_value(items, selected: str) -> str:
    return next((label for label, value in items if value == selected), items[0][0])


def configure_window(window: tk.Tk, title: str, geometry: str) -> None:
    """应用适合 Windows 的紧凑 ttk 风格。"""
    font_name = configure_chinese_font()
    window.title(title)
    window.geometry(geometry)
    window.minsize(1080, 680)

    style = ttk.Style(window)
    if "vista" in style.theme_names():
        style.theme_use("vista")
    default_font = (font_name, 10)
    heading_font = (font_name, 10, "bold")
    style.configure(".", font=default_font)
    style.configure("TLabelframe.Label", font=heading_font)
    style.configure("Primary.TButton", font=(font_name, 11, "bold"), padding=(12, 8))
    style.configure("Secondary.TButton", padding=(10, 7))
    style.configure("Status.TLabel", padding=(8, 6), anchor=tk.W)
    style.configure("Treeview", rowheight=28)
    style.configure("Treeview.Heading", font=heading_font)


class PlotView(ttk.Frame):
    """带导航工具栏、空白占位和保存按钮的嵌入式图形区域。"""

    def __init__(self, parent, save_command):
        super().__init__(parent, padding=(8, 6, 8, 8))
        self.pack(fill=tk.BOTH, expand=True)

        self.figure = Figure(figsize=(9, 6), facecolor="white", layout="constrained")
        self.axes = self.figure.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.figure, master=self)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        action_bar = ttk.Frame(self)
        action_bar.pack(fill=tk.X, pady=(6, 0))
        toolbar_host = ttk.Frame(action_bar)
        toolbar_host.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.toolbar = NavigationToolbar2Tk(
            self.canvas, toolbar_host, pack_toolbar=False
        )
        self.toolbar.update()
        self.toolbar.pack(side=tk.LEFT)

        self.save_button = ttk.Button(
            action_bar,
            text="保存图片",
            command=save_command,
            state=tk.DISABLED,
            style="Secondary.TButton",
        )
        self.save_button.pack(side=tk.RIGHT)
        self.show_placeholder()

    def show_placeholder(self) -> None:
        self.axes.clear()
        self.axes.set_axis_off()
        self.axes.text(
            0.5,
            0.54,
            "仿真结果将在这里显示",
            transform=self.axes.transAxes,
            ha="center",
            va="center",
            fontsize=16,
            color="#556070",
        )
        self.axes.text(
            0.5,
            0.46,
            "设置左侧参数后，点击“开始仿真”",
            transform=self.axes.transAxes,
            ha="center",
            va="center",
            fontsize=10,
            color="#8a94a3",
        )
        self.draw()

    def draw(self) -> None:
        self.canvas.draw()
        self.toolbar.update()

    def set_result_available(self, available: bool = True) -> None:
        self.save_button.configure(state=tk.NORMAL if available else tk.DISABLED)
