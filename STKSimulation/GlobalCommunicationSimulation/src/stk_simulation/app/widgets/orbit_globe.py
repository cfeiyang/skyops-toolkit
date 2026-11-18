"""Offline globe for the link visibility orbit samples."""

from functools import lru_cache
import json
from math import atan2, cos, radians, sin
from pathlib import Path

import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget


EARTH_RADIUS_KM = 6371.0
SPACE_COLOR = "#0f172a"
STATION_COLORS = ("#4da3ff", "#f472b6")
SATELLITE_COLOR = "#ffb703"


@lru_cache(maxsize=1)
def world_rings():
    path = Path(__file__).resolve().parents[2] / "assets" / "world.json"
    world = json.loads(path.read_text(encoding="utf-8"))
    rings = []
    for feature in world["features"]:
        geometry = feature.get("geometry")
        if not geometry:
            continue
        if geometry["type"] == "Polygon":
            rings.extend(geometry["coordinates"])
        elif geometry["type"] == "MultiPolygon":
            for polygon in geometry["coordinates"]:
                rings.extend(polygon)
    return rings


def _unit_vectors(lon_lat):
    lon, lat = np.radians(lon_lat).T
    return np.column_stack((np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)))


@lru_cache(maxsize=1)
def _earth_lines():
    meridians = [[(lon, lat) for lat in range(-90, 91, 4)] for lon in range(0, 360, 30)]
    parallels = [[(lon, lat) for lon in range(-180, 181, 4)] for lat in range(-60, 61, 30)]

    def edges(rings):
        return np.concatenate([np.stack((ring[:-1], ring[1:]), axis=1) for ring in rings])

    outlines = tuple(map(_unit_vectors, world_rings()))
    return (
        edges(map(_unit_vectors, meridians + parallels)),
        edges(_thin_outline(outline, 0.017) for outline in outlines),
        edges(_thin_outline(outline, 0.006) for outline in outlines),
    )


def _thin_outline(outline, spacing):
    distance = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(outline, axis=0), axis=1))]
    indices = np.unique(np.r_[distance.searchsorted(np.arange(0, distance[-1], spacing)), len(outline) - 1])
    return outline[indices] if indices.size >= 4 else outline


def _draw_edges(painter, edges, center, scale, *, front=False):
    """Draw projected segments, clipping at the camera plane when requested."""
    edges = edges[np.isfinite(edges).all(axis=(1, 2))]
    if front:
        edges = edges[(edges[:, :, 2] >= 0).any(axis=1)].copy()
        for inside, outside in ((0, 1), (1, 0)):
            crosses = edges[:, outside, 2] < 0
            a, b = edges[crosses, inside], edges[crosses, outside]
            ratio = (a[:, 2] / (a[:, 2] - b[:, 2]))[:, None]
            edges[crosses, outside] = a + (b - a) * ratio
    pixels = edges[:, :, :2] * (scale, -scale) + (center.x(), center.y())
    path = QPainterPath()
    for (x0, y0), (x1, y1) in pixels:
        path.moveTo(x0, y0)
        path.lineTo(x1, y1)
    painter.drawPath(path)


class OrbitGlobeWidget(QWidget):
    """Interactive orthographic projection of the sampled 3D orbit."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(440)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._orbit = None
        self._position = 0.0
        self._drag_at = None
        self._azimuth = 0.0
        self._elevation = radians(23)
        self._zoom = 1.0
        self._extent = 1.15
        self._orbit_edges = np.empty((0, 2, 3))
        self._station_vectors = np.empty((0, 3))
        self._stations = ()
        self._satellite = ""

    def set_data(self, orbit, stations, satellite_name):
        self._orbit = orbit
        self._position = 0.0
        self._stations = tuple(stations[:2])
        self._satellite = satellite_name
        self._zoom = 1.0
        self._elevation = radians(23)
        if self._stations:
            self._station_vectors = _unit_vectors([(st.longitude_deg, st.latitude_deg) for st in self._stations])
        else:
            self._station_vectors = np.empty((0, 3))
        self._orbit_edges = np.empty((0, 2, 3))
        self._extent = 1.15
        if orbit is not None and orbit.elapsed_sec:
            points = orbit.inertial_km / EARTH_RADIUS_KM
            distances = np.linalg.norm(points, axis=1)
            valid = np.flatnonzero(np.isfinite(distances))
            if valid.size:
                self._extent = max(self._extent, float(distances[valid].max()))
                x, y, _ = points[valid[0]]
                self._azimuth = atan2(y, x) - radians(22)
            indices = np.linspace(0, len(points) - 1, min(len(points), 4096), dtype=int)
            samples = points[indices]
            self._orbit_edges = np.stack((samples[:-1], samples[1:]), axis=1)
            if valid.size < len(points):
                missing = np.r_[0, np.cumsum(~np.isfinite(distances))]
                self._orbit_edges = self._orbit_edges[missing[indices[1:] + 1] == missing[indices[:-1]]]
        self.update()

    def set_position(self, position):
        self._position = position
        self.update()

    def _camera(self):
        ca, sa = cos(self._azimuth), sin(self._azimuth)
        ce, se = cos(self._elevation), sin(self._elevation)
        return np.array([[-sa, ca, 0], [-se * ca, -se * sa, ce], [ce * ca, ce * sa, se]])

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(SPACE_COLOR))
        camera = self._camera()
        center = QPointF(self.width() / 2, self.height() / 2)
        scale = self._zoom * min(self.width(), self.height()) * 0.46 / self._extent
        orbit = self._orbit
        orientation = np.eye(3)
        satellite = None
        if orbit is not None and orbit.elapsed_sec:
            start = int(self._position)
            end = min(start + 1, len(orbit.elapsed_sec) - 1)
            fraction = self._position - start
            orientation = (1 - fraction) * orbit.inertial_to_earth[start] + fraction * orbit.inertial_to_earth[end]
            satellite = ((1 - fraction) * orbit.inertial_km[start] + fraction * orbit.inertial_km[end]) / EARTH_RADIUS_KM

        projected_orbit = self._orbit_edges @ camera.T
        painter.setPen(QPen(QColor("#296981"), 1.2))
        _draw_edges(painter, projected_orbit, center, scale)

        light = QPointF(center.x() - 0.38 * scale, center.y() - 0.43 * scale)
        ocean = QRadialGradient(light, 1.65 * scale)
        ocean.setColorAt(0, QColor("#245581"))
        ocean.setColorAt(1, QColor("#102038"))
        painter.setBrush(ocean)
        painter.setPen(QPen(QColor("#6194bd"), 1.4))
        painter.drawEllipse(center, scale, scale)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        earth_view = orientation @ camera.T
        graticule, outline, detailed_outline = _earth_lines()
        painter.setPen(QPen(QColor("#3b6482"), 0.7))
        _draw_edges(painter, graticule @ earth_view, center, scale, front=True)
        painter.setPen(QPen(QColor("#72a6bb"), 0.85))
        coastline = detailed_outline if scale >= 180 else outline
        _draw_edges(painter, coastline @ earth_view, center, scale, front=True)
        painter.setPen(QPen(QColor("#22d3ee"), 1.65))
        _draw_edges(painter, projected_orbit, center, scale, front=True)

        for station, (x, y, depth), color in zip(self._stations, self._station_vectors @ earth_view, STATION_COLORS):
            if depth >= 0:
                point = QPointF(center.x() + scale * x, center.y() - scale * y)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(color))
                painter.drawEllipse(point, 4.5, 4.5)
                if scale >= 120:
                    painter.setPen(QColor(color))
                    painter.drawText(point + QPointF(8, -5), station.name)

        if satellite is not None and np.isfinite(satellite).all():
            x, y, depth = camera @ satellite
            if depth >= 0 or x * x + y * y >= 1:
                point = QPointF(center.x() + scale * x, center.y() - scale * y)
                painter.setPen(QPen(QColor("#674c16"), 2))
                painter.setBrush(QColor(SATELLITE_COLOR))
                painter.drawEllipse(point, 6, 6)
                painter.setPen(QColor(SATELLITE_COLOR))
                painter.drawText(point + QPointF(11, -8), self._satellite)
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_at = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        if self._drag_at is not None:
            delta = event.position() - self._drag_at
            self._drag_at = event.position()
            self._azimuth -= delta.x() * 0.008
            self._elevation = max(-1.55, min(1.55, self._elevation + delta.y() * 0.008))
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_at = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)

    def wheelEvent(self, event):
        self._zoom = max(0.6, min(9.0, self._zoom * 1.15 ** (event.angleDelta().y() / 120)))
        event.accept()
        self.update()
