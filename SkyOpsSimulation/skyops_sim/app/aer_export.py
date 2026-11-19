"""AER window selection and exports for link visibility."""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from html import escape

from PySide6.QtGui import QPageSize, QTextDocument
from PySide6.QtPrintSupport import QPrinter

from skyops_sim.simulations.link_visibility.config import AccessWindow, LinkVisibilityResult


@dataclass(frozen=True)
class AERWindow:
    access: AccessWindow
    rows: tuple[tuple[str, ...], ...]

    @property
    def number(self) -> int:
        return self.access.access_number


@dataclass(frozen=True)
class AERGroup:
    label: str
    code: str
    ssc: int
    day: str
    header: tuple[str, ...]
    windows: tuple[AERWindow, ...]
    site_details: tuple[str, ...]
    tle_epoch: str

    def file_stem(self, selection: tuple[AERWindow, ...]) -> str:
        suffix = f"W{selection[0].number}" if len(selection) == 1 else "WAll"
        return f"AER_{self.ssc}_{self.day}_{self.code}_{suffix}"


def build_aer_groups(result: LinkVisibilityResult) -> tuple[AERGroup, ...]:
    station_names = result.station_names[:2]
    stations = {station.name: station for station in result.cfg.stations}
    groups = []
    single_header = ("时间（北京时间）", "方位角(°)", "仰角(°)", "距离(km)")

    def add_group(label, code, header, names, windows):
        if not windows:
            return
        details = []
        for name in names:
            station = stations.get(name)
            if station:
                details.append(f"{name}：纬度 {station.latitude_deg:.6f}°，经度 {station.longitude_deg:.6f}°")

        groups.append(AERGroup(
            label, code, result.cfg.satellite.ssc, result.start_time[:10],
            header, tuple(windows), tuple(details), result.tle_epoch,
        ))

    def values(record):
        if record is None:
            return ("", "", "")
        return f"{record.azimuth_deg:.2f}", f"{record.elevation_deg:.2f}", f"{record.range_km:.2f}"

    if len(station_names) == 2:
        header = (single_header[0], *(name + field for name in station_names for field in single_header[1:]))
        samples = defaultdict(lambda: defaultdict(dict))
        for record in result.aer_records:
            samples[record.access_number][record.time][record.station_name] = record
        windows = []
        for window in sorted(result.windows, key=lambda access: access.start_time):
            rows = tuple(
                (time, *values(by_station.get(station_names[0])), *values(by_station.get(station_names[1])))
                for time, by_station in sorted(samples[window.access_number].items())
            )
            if rows:
                windows.append(AERWindow(window, rows))
        add_group("两地通信", "COMM", header, station_names, windows)

    for number, name in enumerate(station_names, start=1):
        samples = defaultdict(list)
        for record in result.station_aer.get(name, ()):
            samples[record.access_number].append((record.time, *values(record)))
        windows = [
            AERWindow(window, tuple(sorted(samples[window.access_number])))
            for window in sorted(result.station_windows.get(name, ()), key=lambda access: access.start_time)
            if samples[window.access_number]
        ]
        add_group(name, f"P{number}", single_header, (name,), windows)
    return tuple(groups)


def write_aer_csv(path: str, group: AERGroup, windows: tuple[AERWindow, ...]) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(group.header)
        for window in windows:
            writer.writerows(window.rows)


def write_aer_pdf(path: str, group: AERGroup, windows: tuple[AERWindow, ...]) -> None:
    document = QTextDocument()
    other_width = "12.5%" if len(group.header) == 7 else "25%"
    headings = "".join(
        f"<th width='{width}'>{escape(head)}</th>"
        for head, width in zip(group.header, ("25%",) + (other_width,) * (len(group.header) - 1))
    )
    html = [
        "<html><head><style>"
        "body { font-size: 9pt; color: #1e293b; }"
        "td, th { font-size: 8pt; }"
        "h2 { color: #17376b; }"
        "th { background-color: #e7eef7; }"
        "</style></head><body>"
    ]
    for index, window in enumerate(windows):
        access = window.access
        page_break = " style='page-break-before: always'" if index else ""
        html.append(f"<h2{page_break}>{escape(group.label)} · 窗口 {window.number}</h2>")
        if index == 0:
            details = [*group.site_details, f"仿真日期 {group.day}　SSC {group.ssc}"]
            if group.tle_epoch:
                details.append(f"星历历元 {group.tle_epoch}（北京时间）")
            html.append("<p>" + "<br>".join(map(escape, details)) + "</p>")
        time_label = "通信时间" if group.code == "COMM" else "可用时间"
        html.append(f"<p>{time_label}（北京时间） {escape(access.start_time)} 至 {escape(access.stop_time)}</p>")
        html.append(f"<table border='0.5' cellspacing='0' cellpadding='2' width='100%'><thead><tr>{headings}</tr></thead>")
        for row in window.rows:
            html.append("<tr>" + "".join(f"<td><nobr>{escape(cell)}</nobr></td>" for cell in row) + "</tr>")
        html.append("</table>")
    html.append("</body></html>")
    document.setHtml("".join(html))
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(path)
    printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    printer.setDocName("AER 数据")
    document.print_(printer)
    if printer.printerState() == QPrinter.PrinterState.Error:
        raise OSError("无法写入 PDF 文件。")
