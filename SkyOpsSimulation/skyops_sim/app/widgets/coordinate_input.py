"""地面站经纬度输入。方向单独选择，计算统一使用带符号的十进制度。"""

from math import copysign

from PySide6.QtCore import QSignalBlocker
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QHBoxLayout, QSpinBox,
    QStackedWidget, QWidget,
)

_SECONDS_SCALE = 1_000


class CoordinateInput(QWidget):
    def __init__(self, latitude: bool, coordinate: float) -> None:
        super().__init__()
        self._limit = 90 if latitude else 180
        self.direction = QComboBox()
        self.direction.addItems(("北纬 N", "南纬 S") if latitude else ("东经 E", "西经 W"))
        self.direction.setAccessibleName("纬度方向" if latitude else "经度方向")
        self.decimal = QDoubleSpinBox()
        self.decimal.setDecimals(8)
        self.decimal.setRange(-self._limit, self._limit)
        self.decimal.setSuffix("°")
        self.decimal.setKeyboardTracking(False)
        self.decimal.setAccessibleName("十进制纬度" if latitude else "十进制经度")
        self.decimal.valueChanged.connect(self._accept_signed_decimal)

        self.degrees, self.minutes = QSpinBox(), QSpinBox()
        self.degrees.setRange(0, self._limit)
        self.seconds = QDoubleSpinBox()
        self.seconds.setDecimals(3)
        self.degrees.valueChanged.connect(self._update_fraction_limits)
        self._update_fraction_limits(0)
        dms = QWidget()
        row = QHBoxLayout(dms)
        row.setContentsMargins(0, 0, 0, 0)
        for field, suffix, unit in (
            (self.degrees, "°", "度"), (self.minutes, "′", "分"), (self.seconds, "″", "秒"),
        ):
            field.setSuffix(suffix)
            field.setAccessibleName(("纬度" if latitude else "经度") + unit)
            row.addWidget(field, 2 if field is self.seconds else 1)

        self._formats = QStackedWidget()
        self._formats.addWidget(self.decimal)
        self._formats.addWidget(dms)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.direction)
        layout.addWidget(self._formats, 1)
        self.set_value(coordinate)

    def _accept_signed_decimal(self, value: float) -> None:
        if value < 0:
            self.direction.setCurrentIndex(1)
            with QSignalBlocker(self.decimal):
                self.decimal.setValue(-value)

    def _update_fraction_limits(self, degrees: int) -> None:
        at_limit = degrees == self._limit
        self.minutes.setMaximum(0 if at_limit else 59)
        self.seconds.setMaximum(0 if at_limit else 59.999)

    def set_value(self, value: float) -> None:
        self.direction.setCurrentIndex(int(copysign(1.0, value) < 0))
        self.decimal.setValue(abs(value))
        units = round(abs(value) * 3600 * _SECONDS_SCALE)
        degrees, remainder = divmod(units, 3600 * _SECONDS_SCALE)
        minutes, seconds = divmod(remainder, 60 * _SECONDS_SCALE)
        self.degrees.setValue(degrees)
        self.minutes.setValue(minutes)
        self.seconds.setValue(seconds / _SECONDS_SCALE)
        # Preserve the original precision when the user only switches formats.
        self._magnitude = abs(value)
        self._displayed_decimal = self.decimal.value()
        self._displayed_dms = self._dms_parts()

    def _dms_parts(self) -> tuple[int, int, float]:
        return self.degrees.value(), self.minutes.value(), self.seconds.value()

    def value(self) -> float:
        if self._formats.currentIndex() == 0:
            self.decimal.interpretText()
            shown = self.decimal.value()
            magnitude = self._magnitude if shown == self._displayed_decimal else shown
        else:
            degrees, minutes, seconds = parts = self._dms_parts()
            magnitude = self._magnitude if parts == self._displayed_dms else degrees + minutes / 60 + seconds / 3600
        return -magnitude if self.direction.currentIndex() == 1 else magnitude

    def set_dms(self, enabled: bool) -> None:
        if self._formats.currentIndex() != int(enabled):
            value = self.value()
            self.set_value(value)
            self._formats.setCurrentIndex(int(enabled))
