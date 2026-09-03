"""地面站新增与编辑对话框。"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from stk_simulation.simulations.global_coverage.presets import StationConfig


class StationDialog(QDialog):
    def __init__(self, parent: QWidget, title: str, station: StationConfig) -> None:
        super().__init__(parent)
        self.result: StationConfig | None = None
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(380)

        self.name_field = QLineEdit(station.name)
        self.lat_field = QLineEdit(f"{station.lat:.8g}")
        self.lon_field = QLineEdit(f"{station.lon:.8g}")
        self.alt_field = QLineEdit(f"{station.alt:g}")
        self.elevation_field = QLineEdit(f"{station.min_elevation:g}")

        form = QFormLayout()
        form.addRow("地面站名称", self.name_field)
        form.addRow("纬度 / °", self.lat_field)
        form.addRow("经度 / °", self.lon_field)
        form.addRow("高度 / km", self.alt_field)
        form.addRow("最低仰角 / °", self.elevation_field)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)
        self.name_field.selectAll()
        self.name_field.setFocus()

    @classmethod
    def show(
        cls, parent: QWidget, title: str, station: StationConfig
    ) -> StationConfig | None:
        dialog = cls(parent, title, station)
        dialog.exec()
        return dialog.result

    def _accept(self) -> None:
        try:
            station = StationConfig(
                name=self.name_field.text().strip(),
                lat=float(self.lat_field.text()),
                lon=float(self.lon_field.text()),
                alt=float(self.alt_field.text()),
                min_elevation=float(self.elevation_field.text()),
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
            QMessageBox.critical(self, "参数错误", str(error))
            return
        self.result = station
        self.accept()
