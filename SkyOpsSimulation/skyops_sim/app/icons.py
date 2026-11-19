"""Local Lucide icons for application controls."""

from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QPushButton


ASSETS = Path(__file__).resolve().parents[1] / "assets"


@lru_cache(maxsize=None)
def icon(name: str, ink: str = "#345880") -> QIcon:
    artwork = (ASSETS / "icons" / f"{name}.svg").read_bytes()
    renderer = QSvgRenderer(QByteArray(artwork.replace(b"currentColor", ink.encode("ascii"))))
    result = QIcon()
    for scale in (1, 2):
        size = 18 * scale
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(painter, QRectF(0, 0, size, size))
        painter.end()
        pixmap.setDevicePixelRatio(scale)
        result.addPixmap(pixmap)
    return result


def apply_icon(button: QPushButton, name: str, *, primary: bool = False) -> None:
    button.setIcon(icon(name, "#ffffff" if primary else "#345880"))
    button.setIconSize(QSize(18, 18))


def action_button(text: str, name: str, *, primary: bool = False) -> QPushButton:
    button = QPushButton(text)
    apply_icon(button, name, primary=primary)
    if primary:
        button.setObjectName("primaryButton")
    return button

