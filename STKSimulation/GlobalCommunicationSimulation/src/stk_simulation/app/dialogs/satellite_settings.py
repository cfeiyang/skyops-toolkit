"""Edit and remember the common satellite and TLE source."""

import re
from pathlib import Path
from urllib.parse import urlparse

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QSpinBox, QVBoxLayout, QWidget,
)

from stk_simulation.app.icons import action_button
from stk_simulation.infrastructure.reference_satellite import ReferenceSatellite
from stk_simulation.infrastructure.tle import default_tle_url, read_local_tle


def load_reference_satellite() -> ReferenceSatellite:
    settings = QSettings("SkyOps", "Simulation")
    default = ReferenceSatellite()
    try:
        ssc = int(settings.value("satellite/ssc", default.ssc))
    except (TypeError, ValueError):
        ssc = default.ssc
    return ReferenceSatellite(
        name=str(settings.value("satellite/name", default.name)),
        ssc=ssc,
        tle_url=str(settings.value("satellite/url", "")),
        tle_file=str(settings.value("satellite/file", "")),
    )


def save_reference_satellite(profile: ReferenceSatellite) -> None:
    settings = QSettings("SkyOps", "Simulation")
    settings.setValue("satellite/name", profile.name)
    settings.setValue("satellite/ssc", profile.ssc)
    settings.setValue("satellite/url", profile.tle_url)
    settings.setValue("satellite/file", profile.tle_file)


class SatelliteSettingsDialog(QDialog):
    def __init__(self, profile, parent=None):
        super().__init__(parent)
        self.profile = profile
        self.setWindowTitle("卫星设置")
        self.setMinimumWidth(580)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 15, 18, 16)
        layout.setSpacing(11)

        form = QFormLayout()
        form.setSpacing(10)
        self.name = QLineEdit(profile.name)
        self.ssc = QSpinBox()
        self.ssc.setRange(1, 99999)
        self.ssc.setValue(profile.ssc)
        self.mode = QComboBox()
        self.mode.addItem("运行时在线更新", "online")
        self.mode.addItem("本地 TLE 文件", "file")
        form.addRow("卫星名称", self.name)
        form.addRow("目录号（SSC）", self.ssc)
        form.addRow("轨道数据来源", self.mode)
        layout.addLayout(form)

        self.online = QWidget()
        online = QVBoxLayout(self.online)
        online.setContentsMargins(0, 0, 0, 0)
        online.setSpacing(5)
        self.url = QLineEdit(profile.tle_url)
        self.url.setPlaceholderText("使用 CelesTrak")
        self.url_label = QLabel()
        self.url_label.setObjectName("hintLabel")
        self.url_label.setWordWrap(True)
        online.addWidget(QLabel("自定义 HTTPS 地址（可选）"))
        online.addWidget(self.url)
        online.addWidget(self.url_label)
        layout.addWidget(self.online)

        self.local = QWidget()
        local = QVBoxLayout(self.local)
        local.setContentsMargins(0, 0, 0, 0)
        local.setSpacing(5)
        file_row = QHBoxLayout()
        self.file = QLineEdit(profile.tle_file)
        browse = action_button("浏览", "folder-open")
        browse.clicked.connect(self._browse)
        file_row.addWidget(self.file, 1)
        file_row.addWidget(browse)
        local.addWidget(QLabel("TLE 文件"))
        local.addLayout(file_row)
        layout.addWidget(self.local)

        self.error = QLabel()
        self.error.setObjectName("workbenchStatus")
        self.error.setProperty("problem", True)
        self.error.setWordWrap(True)
        self.error.hide()
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("保存")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.mode.setCurrentIndex(1 if profile.tle_file else 0)
        self.mode.currentIndexChanged.connect(self._refresh)
        self.ssc.valueChanged.connect(self._refresh)
        self._refresh()

    def _refresh(self):
        online = self.mode.currentData() == "online"
        self.online.setVisible(online)
        self.local.setVisible(not online)
        self.url_label.setText("默认地址：" + default_tle_url(self.ssc.value()))

    def _browse(self):
        file, _ = QFileDialog.getOpenFileName(
            self, "选择 TLE 文件", self.file.text(), "TLE 文件 (*.tle *.txt)"
        )
        if file:
            self.file.setText(str(Path(file)))

    def accept(self):
        satellite_name = self.name.text().strip()
        url = self.url.text().strip()
        local = self.file.text().strip() if self.mode.currentData() == "file" else ""
        ssc = self.ssc.value()
        try:
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", satellite_name):
                raise ValueError("卫星名称须以英文字母开头，可使用字母、数字和下划线。")
            if url:
                parsed = urlparse(url.replace("{ssc}", str(ssc)))
                if parsed.scheme != "https" or not parsed.hostname:
                    raise ValueError("自定义地址须为有效的 HTTPS URL。")
            if self.mode.currentData() == "file":
                if not local:
                    raise ValueError("请选择本地 TLE 文件。")
                read_local_tle(local, ssc)
        except (OSError, UnicodeError, ValueError) as error:
            self.error.setText(str(error))
            self.error.show()
            return
        self.profile = ReferenceSatellite(satellite_name, ssc, url, local)
        super().accept()

