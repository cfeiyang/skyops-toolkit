"""地面站新增与编辑对话框。"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
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
        self.lat_field = _number_field(
            station.lat, -90.0, 90.0, 6, 0.0001, " °"
        )
        self.lon_field = _number_field(
            station.lon, -180.0, 180.0, 6, 0.0001, " °"
        )
        self.alt_field = _number_field(
            station.alt * 1000.0, -1000.0, 100000.0, 2, 1.0, " m"
        )
        self.elevation_field = _number_field(
            station.min_elevation, 0.0, 90.0, 2, 1.0, " °"
        )

        form = QFormLayout()
        form.addRow("地面站名称", self.name_field)
        form.addRow("纬度（北正南负）", self.lat_field)
        form.addRow("经度（东正西负）", self.lon_field)
        form.addRow("海拔高度", self.alt_field)
        form.addRow("最低仰角", self.elevation_field)

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
        name = self.name_field.text().strip()
        if not name:
            QMessageBox.critical(self, "参数错误", "地面站名称不能为空。")
            return
        self.result = StationConfig(
            name=name,
            lat=self.lat_field.value(),
            lon=self.lon_field.value(),
            alt=self.alt_field.value() / 1000.0,
            min_elevation=self.elevation_field.value(),
        )
        self.accept()


def _number_field(
    value: float,
    minimum: float,
    maximum: float,
    decimals: int,
    step: float,
    suffix: str,
) -> QDoubleSpinBox:
    field = QDoubleSpinBox()
    field.setRange(minimum, maximum)
    field.setDecimals(decimals)
    field.setSingleStep(step)
    field.setSuffix(suffix)
    field.setValue(value)
    return field
