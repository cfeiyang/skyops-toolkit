"""在仿真参数页内选择计算引擎及 STK 会话。"""

from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QWidget

from skyops_sim.simulations.common import STKConfig


class EngineSelection(QWidget):
    def __init__(self, config: STKConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        engine_label = QLabel("计算引擎")
        self.engine = QComboBox()
        self.engine.addItem("Python", "python")
        self.engine.addItem("STK 12", "stk")
        self.engine.setCurrentIndex(max(0, self.engine.findData(config.engine)))
        engine_label.setBuddy(self.engine)
        self.mode_label = QLabel("STK 会话")
        self.mode = QComboBox()
        self.mode.addItem("新建 STK 实例", "new")
        self.mode.addItem("连接已运行的 STK", "running")
        self.mode.setCurrentIndex(max(0, self.mode.findData(config.mode)))
        self.mode_label.setBuddy(self.mode)
        row.addWidget(engine_label)
        row.addWidget(self.engine)
        row.addWidget(self.mode_label)
        row.addWidget(self.mode)
        self.engine.currentIndexChanged.connect(self._update_mode_visibility)
        self._update_mode_visibility()

    def _update_mode_visibility(self) -> None:
        visible = self.engine.currentData() == "stk"
        self.mode_label.setVisible(visible)
        self.mode.setVisible(visible)

    def config(self) -> STKConfig:
        return STKConfig(mode=self.mode.currentData(), engine=self.engine.currentData())
