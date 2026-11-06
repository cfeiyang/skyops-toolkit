"""PySide6 中复用的 Matplotlib 结果视图。"""

from __future__ import annotations

from pathlib import Path

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from stk_simulation.utils.plotting import configure_chinese_font, save_axes_image


class PlotWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        configure_chinese_font()
        self._default_image_path: Path | None = None
        self.figure = Figure(figsize=(10, 6), facecolor="white", layout="constrained")
        self.axes = self.figure.add_subplot(111)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        self.save_button = QPushButton("保存图片")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self._save_image)

        tools = QHBoxLayout()
        tools.setContentsMargins(0, 0, 0, 0)
        tools.addWidget(self.toolbar)
        tools.addStretch(1)
        tools.addWidget(self.save_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self.canvas, 1)
        layout.addLayout(tools)
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
            "完成参数设置后，点击“开始仿真”",
            transform=self.axes.transAxes,
            ha="center",
            va="center",
            fontsize=10,
            color="#8a94a3",
        )
        self.canvas.draw_idle()

    def show_result(self, result, renderer) -> None:
        renderer(result, self.axes)
        self.canvas.draw_idle()
        self.toolbar.update()
        self._default_image_path = result.output.image_path
        self.save_button.setEnabled(True)

    def set_busy(self, busy: bool) -> None:
        self.save_button.setEnabled(not busy and self._default_image_path is not None)

    def _save_image(self) -> None:
        if self._default_image_path is None:
            return
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "保存结果图",
            str(self._default_image_path),
            "PNG 图片 (*.png)",
        )
        if selected:
            save_axes_image(self.axes, selected)
