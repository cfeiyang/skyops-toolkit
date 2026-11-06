"""SkyOps 启动入口：FastAPI + Jinja2 服务端渲染。

基于原 SatLog 的框架无关服务层（tle_service / visibility_service /
excel_service / record_logic），仅替换界面层为 FastAPI 页面。
"""

from __future__ import annotations

import csv
import io
import os
from collections import OrderedDict
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote
from uuid import uuid4

import numpy as np
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import OPTIONS
from app.excel_service import (
    PERMISSION_MESSAGE,
    RecordValidationError,
    append_record_to_excel,
    get_excel_status,
    load_history,
    parse_record_date,
    validate_record,
)
from app.paths import DATA_DIR, PROJECT_ROOT
from app.record_logic import build_record, default_draft, split_location
from app import tle_service, visibility_service
from app.visibility_service import StationConfig

app = FastAPI(title="SkyOps")
STATIC_DIR = PROJECT_ROOT / "app" / "static"
TEMPLATE_DIR = PROJECT_ROOT / "app" / "templates"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

# 导出缓存：内存中保留最近几次导出的文件（令牌 -> (文件名, 内容字节, MIME)）
_EXPORTS: "OrderedDict[str, Tuple[str, bytes, str]]" = OrderedDict()
_EXPORT_LIMIT = 400


def _store_export(filename: str, content: bytes, media_type: str) -> str:
    token = uuid4().hex
    _EXPORTS[token] = (filename, content, media_type)
    while len(_EXPORTS) > _EXPORT_LIMIT:
        _EXPORTS.popitem(last=False)
    return token


def _aer_csv_bytes(rows: List[Dict[str, Any]]) -> bytes:
    """AER 记录 → CSV（带 UTF-8 BOM，Excel 直开不乱码）。"""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["时间（北京时间）", "方位角(°)", "仰角(°)", "距离(km)"])
    for row in rows:
        writer.writerow([row["time"], row["az"], row["el"], row["range"]])
    return ("\ufeff" + buffer.getvalue()).encode("utf-8")


def _aer_comm_csv_bytes(rows: List[Dict[str, Any]], label1: str = "地点1", label2: str = "地点2") -> bytes:
    """两地通信 AER → CSV（宽表：时间 + 地点1 AER + 地点2 AER 并排）。"""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["时间（北京时间）",
                     f"{label1}方位角(°)", f"{label1}仰角(°)", f"{label1}距离(km)",
                     f"{label2}方位角(°)", f"{label2}仰角(°)", f"{label2}距离(km)"])
    for row in rows:
        writer.writerow([row["time"], row["a_az"], row["a_el"], row["a_range"],
                         row["b_az"], row["b_el"], row["b_range"]])
    return ("\ufeff" + buffer.getvalue()).encode("utf-8")


_CJK_FONT_NAME = ""


def _cjk_font() -> str:
    """注册中文字体（优先 SimHei），返回 reportlab 字体名。"""
    global _CJK_FONT_NAME
    if _CJK_FONT_NAME:
        return _CJK_FONT_NAME
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    for path in (
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\Deng.ttf",
        r"C:\Windows\Fonts\simsun.ttc",
    ):
        if not os.path.exists(path):
            continue
        try:
            kwargs = {"subfontIndex": 0} if path.lower().endswith(".ttc") else {}
            pdfmetrics.registerFont(TTFont("SkyOpsCJK", path, **kwargs))
            _CJK_FONT_NAME = "SkyOpsCJK"
            return _CJK_FONT_NAME
        except Exception:  # noqa: BLE001
            continue
    _CJK_FONT_NAME = "Helvetica"
    return _CJK_FONT_NAME


def _geo_text(lat: float, lon: float) -> str:
    """经纬度 → 带半球的中文写法（南纬/北纬、东经/西经），不出现负号。"""
    ns = "北纬" if lat >= 0 else "南纬"
    ew = "东经" if lon >= 0 else "西经"
    return f"{ns} {abs(lat):.4f}°，{ew} {abs(lon):.4f}°"


def _build_pdf_report(report: Dict[str, Any]) -> bytes:
    """生成 AER 导出 PDF。

    report 两种形式：
    - 单窗口：{"header": str, "aer": rows}
    - 多窗口合并：{"sections": [{"title": str, "header": str|空, "aer": rows}, ...]}
      每个 section 强制从新一页开始，窗口之间不会混排。
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (PageBreak, Paragraph, SimpleDocTemplate,
                                    Spacer, Table, TableStyle)

    font = _cjk_font()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=15 * mm, rightMargin=15 * mm, topMargin=14 * mm, bottomMargin=14 * mm,
        title="AER 导出", author="SkyOps",
    )
    header_style = ParagraphStyle("h", fontName=font, fontSize=10.5, leading=16,
                                  textColor=colors.HexColor("#0f172a"), spaceAfter=6)
    title_style = ParagraphStyle("st", fontName=font, fontSize=12, leading=17,
                                 textColor=colors.HexColor("#1e3a8a"), spaceAfter=4)

    def build_table(rows):
        header_row = rows[0] if rows else []
        n_cols = len(header_row)
        if n_cols == 4:
            col_widths = [46 * mm, 30 * mm, 30 * mm, 30 * mm]
        elif n_cols == 7:
            col_widths = [36 * mm, 24 * mm, 20 * mm, 22 * mm, 24 * mm, 20 * mm, 22 * mm]
        else:
            col_widths = [168 * mm / max(1, n_cols)] * n_cols
        table = Table(rows, colWidths=col_widths, repeatRows=1, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), font),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#334155")),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
        ]))
        return table

    sections = report.get("sections")
    if sections:
        story = []
        for idx, sec in enumerate(sections):
            if idx > 0:
                story.append(PageBreak())          # 每个窗口新起一页
            if sec.get("title"):
                story.append(Paragraph(sec["title"], title_style))
            if sec.get("header"):
                story.append(Paragraph(sec["header"], header_style))
            story.append(Spacer(1, 4))
            story.append(build_table(sec["aer"]))
    else:
        story = [Paragraph(report["header"], header_style), Spacer(1, 4), build_table(report["aer"])]
    doc.build(story)
    return buffer.getvalue()

_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
_LOCAL_TZ = visibility_service.LOCAL_TZ


def _base_context(request: Request, active: str, **extra: Any) -> Dict[str, Any]:
    context = {
        "request": request,
        "active": active,
        "app_name": OPTIONS["应用名称"],
        "company": OPTIONS.get("公司名称", ""),
        "version": OPTIONS.get("版本", ""),
        "options": OPTIONS,
    }
    context.update(extra)
    return context


# --------------------------------------------------------------------------- #
# TLE 读取
# --------------------------------------------------------------------------- #
def _load_tle_record() -> Dict[str, Any]:
    satellite = OPTIONS["卫星"]
    ssc = int(satellite["SSC"])
    url = OPTIONS["TLE地址模板"].format(ssc=ssc)
    try:
        record = tle_service.load_latest_tle(
            url, DATA_DIR, ssc, timeout=8.0,
            max_cache_age=float(OPTIONS.get("TLE缓存有效期（秒）", 7200)),
        )
    except (RuntimeError, OSError, ValueError) as error:
        return {"ok": False, "message": str(error)}
    try:
        name, line1, line2 = tle_service.read_tle(record.path)
        epoch = tle_service.parse_epoch(line1)
    except (OSError, ValueError) as error:
        return {"ok": False, "message": f"本地 TLE 缓存无效：{error}"}
    age_hours = (datetime.now(timezone.utc) - epoch).total_seconds() / 3600.0
    return {
        "ok": True,
        "source": "在线 / 缓存",
        "name": name,
        "line1": line1,
        "line2": line2,
        "epoch_local": epoch.astimezone(_LOCAL_TZ).strftime(_TIME_FORMAT),
        "age_hours": age_hours,
        "cache_time": datetime.fromtimestamp(record.path.stat().st_mtime).strftime(_TIME_FORMAT),
    }


def _parse_uploaded_tle(text: str) -> Dict[str, Any]:
    name, line1, line2 = tle_service.parse_tle_text(text)
    epoch = tle_service.parse_epoch(line1)
    age_hours = (datetime.now(timezone.utc) - epoch).total_seconds() / 3600.0
    return {
        "ok": True,
        "source": "上传",
        "name": name,
        "line1": line1,
        "line2": line2,
        "epoch_local": epoch.astimezone(_LOCAL_TZ).strftime(_TIME_FORMAT),
        "age_hours": age_hours,
        "cache_time": "—",
    }


# --------------------------------------------------------------------------- #
# 站点与掩角解析
# --------------------------------------------------------------------------- #
def _dms_to_decimal(degrees: float, minutes: float, seconds: float) -> float:
    sign = -1.0 if degrees < 0 else 1.0
    return sign * (abs(degrees) + minutes / 60.0 + seconds / 3600.0)


def _decimal_to_dms(value: float) -> Tuple[float, float, float]:
    """十进制度 → (度, 分, 秒)，符号放在度上。"""
    sign = -1.0 if value < 0 else 1.0
    v = abs(value)
    d = int(v)
    m_full = (v - d) * 60.0
    m = int(m_full)
    s = (m_full - m) * 60.0
    return (sign * d, m, round(s, 2))


def _coord_from_form(form, prefix: str, label: str) -> Tuple[float, float, str]:
    """从表单解析某地点的经纬度（支持度分秒 / 十进制），返回 (纬度, 经度, 模式)。"""
    mode = form.get(f"{prefix}_mode", "dms")
    if mode == "decimal":
        raw_lat = (form.get(f"{prefix}_lat_dec") or "").strip()
        raw_lon = (form.get(f"{prefix}_lon_dec") or "").strip()
        if not raw_lat or not raw_lon:
            raise ValueError(f"请填写「{label}」的十进制纬度与经度。")
        return _parse_float(raw_lat, 0.0), _parse_float(raw_lon, 0.0), mode
    raw_lat_deg = (form.get(f"{prefix}_lat_deg") or "").strip()
    raw_lon_deg = (form.get(f"{prefix}_lon_deg") or "").strip()
    if not raw_lat_deg or not raw_lon_deg:
        raise ValueError(f"请填写「{label}」的度分秒经纬度（至少度）。")
    lat = _dms_to_decimal(
        _parse_float(raw_lat_deg, 0.0),
        _parse_float(form.get(f"{prefix}_lat_min", ""), 0.0),
        _parse_float(form.get(f"{prefix}_lat_sec", ""), 0.0),
    )
    lon = _dms_to_decimal(
        _parse_float(raw_lon_deg, 0.0),
        _parse_float(form.get(f"{prefix}_lon_min", ""), 0.0),
        _parse_float(form.get(f"{prefix}_lon_sec", ""), 0.0),
    )
    return lat, lon, mode


def _echo_location(context: Dict[str, Any], prefix: str, name: str, mode: str,
                   lat: float, lon: float, min_el: float, gso: float) -> None:
    """把一个地点的解析结果写回表单回显字段。"""
    dms_lat = _decimal_to_dms(lat)
    dms_lon = _decimal_to_dms(lon)
    context[f"{prefix}_name"] = name
    context[f"{prefix}_mode"] = mode
    context[f"{prefix}_lat_deg"] = dms_lat[0]
    context[f"{prefix}_lat_min"] = dms_lat[1]
    context[f"{prefix}_lat_sec"] = dms_lat[2]
    context[f"{prefix}_lon_deg"] = dms_lon[0]
    context[f"{prefix}_lon_min"] = dms_lon[1]
    context[f"{prefix}_lon_sec"] = dms_lon[2]
    context[f"{prefix}_lat_dec"] = lat
    context[f"{prefix}_lon_dec"] = lon
    context[f"{prefix}_min_el"] = min_el
    context[f"{prefix}_gso"] = gso


def _parse_float(value: str, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_mask(mask_start: List[str], mask_end: List[str], mask_el: List[str]) -> Tuple[Tuple[float, float, float], ...]:
    result = []
    for start, end, el in zip(mask_start, mask_end, mask_el):
        try:
            start_f = float(start)
            end_f = float(end)
            el_f = float(el)
        except (TypeError, ValueError):
            continue
        if start_f == end_f or el_f < 0:
            continue
        result.append((start_f, end_f, el_f))
    return tuple(result)


def _mask_to_string(mask: Tuple[Tuple[float, float, float], ...]) -> str:
    """把掩角表编码为 a,b,c;d,e,f，供前端回传给实时接口。"""
    return ";".join(f"{s:g},{e:g},{v:g}" for s, e, v in mask)


def _parse_mask_string(text: str) -> Tuple[Tuple[float, float, float], ...]:
    """解析 a,b,c;d,e,f 形式的掩角串（与 _mask_to_string 对应）。"""
    result = []
    for chunk in str(text or "").split(";"):
        parts = chunk.split(",")
        if len(parts) != 3:
            continue
        try:
            start, end, elevation = (float(x) for x in parts)
        except ValueError:
            continue
        if start == end or elevation < 0:
            continue
        result.append((start, end, elevation))
    return tuple(result)


# --------------------------------------------------------------------------- #
# 建链可见性
# --------------------------------------------------------------------------- #
_DEFAULT_STATION = OPTIONS.get("默认站点", {})
_LAT_DMS = tuple(_DEFAULT_STATION.get("纬度（度分秒）", (30, 54, 13)))
_LON_DMS = tuple(_DEFAULT_STATION.get("经度（度分秒）", (121, 55, 10)))
while len(_LAT_DMS) < 3:
    _LAT_DMS = _LAT_DMS + (0,)
while len(_LON_DMS) < 3:
    _LON_DMS = _LON_DMS + (0,)
_DEFAULT_ALT = float(_DEFAULT_STATION.get("海拔（米）", 0.0))
_DEFAULT_MIN_EL = float(_DEFAULT_STATION.get("最低仰角（度）", 15.0))
_DEFAULT_GSO_AVOID = float(OPTIONS.get("默认GSO隔离角（度）", 15.0))


def _format_duration(seconds: float) -> str:
    total = int(round(seconds))
    hours, remainder = divmod(total, 3600)
    minutes = remainder // 60
    if hours:
        return f"{hours} 小时 {minutes} 分"
    if minutes:
        return f"{minutes} 分"
    return f"{total} 秒"


def _usable_mask(samples, base_min_el: float, mask) -> np.ndarray:
    az = np.array([s.azimuth_deg for s in samples], dtype=float)
    el = np.array([s.elevation_deg for s in samples], dtype=float)
    minimum = visibility_service._mask_elevation(az, base_min_el, mask)
    return el >= minimum


@app.get("/", response_class=HTMLResponse)
async def index_get(request: Request):
    return _render_visibility(request, None)


@app.post("/", response_class=HTMLResponse)
async def index_post(request: Request):
    form = await request.form()
    return _render_visibility(request, form)


def _render_visibility(request: Request, form) -> HTMLResponse:
    # 上传 TLE 优先
    tle = None
    upload_error = None
    if form is not None:
        uploaded = form.get("tle_file")
        if uploaded is not None and getattr(uploaded, "filename", ""):
            content = uploaded.file.read()
            try:
                tle = _parse_uploaded_tle(content.decode("ascii"))
            except (UnicodeDecodeError, ValueError) as exc:
                upload_error = f"TLE 解析失败：{exc}"
    if tle is None:
        tle = _load_tle_record()

    default_dms_lat = _dms_to_decimal(float(_LAT_DMS[0]), float(_LAT_DMS[1]), float(_LAT_DMS[2]))
    default_dms_lon = _dms_to_decimal(float(_LON_DMS[0]), float(_LON_DMS[1]), float(_LON_DMS[2]))

    context = _base_context(
        request, "visibility",
        tle=tle,
        upload_error=upload_error,
        p1_name="", p1_mode="dms",
        p1_lat_deg="", p1_lat_min="", p1_lat_sec="",
        p1_lon_deg="", p1_lon_min="", p1_lon_sec="",
        p1_lat_dec="", p1_lon_dec="", p1_min_el=_DEFAULT_MIN_EL, p1_gso=_DEFAULT_GSO_AVOID,
        p2_name="海事站", p2_mode="dms",
        p2_lat_deg=_LAT_DMS[0], p2_lat_min=_LAT_DMS[1], p2_lat_sec=_LAT_DMS[2],
        p2_lon_deg=_LON_DMS[0], p2_lon_min=_LON_DMS[1], p2_lon_sec=_LON_DMS[2],
        p2_lat_dec=default_dms_lat, p2_lon_dec=default_dms_lon, p2_min_el=_DEFAULT_MIN_EL, p2_gso=_DEFAULT_GSO_AVOID,
        today=date.today().isoformat(),
        days=1,
        result=None,
        error=None,
    )

    if form is None:
        return templates.TemplateResponse(request, "visibility.html", context)

    # 解析表单（两个地点：名称 + 经纬度[度分秒/十进制] + 最低仰角 + GSO 隔离角）
    try:
        p1_name = (form.get("p1_name") or "").strip()
        p2_name = (form.get("p2_name") or "").strip()
        p1_lat, p1_lon, p1_mode = _coord_from_form(form, "p1", p1_name or "地点1")
        p2_lat, p2_lon, p2_mode = _coord_from_form(form, "p2", p2_name or "地点2")
        p1_min_el = _parse_float(form.get("p1_min_el", ""), _DEFAULT_MIN_EL)
        p1_gso = _parse_float(form.get("p1_gso", ""), _DEFAULT_GSO_AVOID)
        p2_min_el = _parse_float(form.get("p2_min_el", ""), _DEFAULT_MIN_EL)
        p2_gso = _parse_float(form.get("p2_gso", ""), _DEFAULT_GSO_AVOID)
        p1_label = p1_name or "地点1"
        p2_label = p2_name or "地点2"
        try:
            start_date = date.fromisoformat(form.get("start_date", ""))
        except (ValueError, TypeError):
            start_date = date.today()
        days = int(_parse_float(form.get("days", "1"), 1.0))
        days = max(1, min(8, days))

        # 表单回显本次提交的数值
        context["today"] = start_date.isoformat()
        context["days"] = days
        _echo_location(context, "p1", p1_name, p1_mode, p1_lat, p1_lon, p1_min_el, p1_gso)
        _echo_location(context, "p2", p2_name, p2_mode, p2_lat, p2_lon, p2_min_el, p2_gso)

        if not tle.get("ok"):
            raise ValueError("TLE 不可用，无法计算。请上传 TLE 或检查网络后刷新。")

        st1 = StationConfig(name=p1_label, latitude_deg=p1_lat, longitude_deg=p1_lon,
                            altitude_m=0.0, min_elevation_deg=p1_min_el, gso_avoid_deg=p1_gso)
        st2 = StationConfig(name=p2_label, latitude_deg=p2_lat, longitude_deg=p2_lon,
                            altitude_m=0.0, min_elevation_deg=p2_min_el, gso_avoid_deg=p2_gso)
        start_local = datetime.combine(start_date, time.min)
        stop_local = start_local + timedelta(days=days)

        name = OPTIONS["卫星"]["名称"]
        l1, l2 = tle["line1"], tle["line2"]

        vis1 = visibility_service.compute_visibility(l1, l2, name, [st1], start_local, stop_local)
        vis2 = visibility_service.compute_visibility(l1, l2, name, [st2], start_local, stop_local)
        vis_comm = visibility_service.compute_visibility(l1, l2, name, [st1, st2], start_local, stop_local)
        full1 = visibility_service.compute_full_aer(l1, l2, name, st1, start_local, stop_local, step_sec=60.0)
        full2 = visibility_service.compute_full_aer(l1, l2, name, st2, start_local, stop_local, step_sec=60.0)

        # 星下点轨迹（带两端各自的建链状态）
        try:
            track1 = visibility_service.compute_ground_track(l1, l2, name, start_local, stop_local, step_sec=120.0, station=st1)
            track2 = visibility_service.compute_ground_track(l1, l2, name, start_local, stop_local, step_sec=120.0, station=st2)
            track_points = [
                {"time": a.time, "lat": round(a.latitude_deg, 4), "lon": round(a.longitude_deg, 4),
                 "el1": round(a.elevation_deg, 1), "linked1": bool(a.linked),
                 "el2": round(b.elevation_deg, 1), "linked2": bool(b.linked),
                 "comm": bool(a.linked and b.linked)}
                for a, b in zip(track1, track2)
            ]
        except Exception:  # noqa: BLE001
            track_points = []

        elev_labels = [s.time for s in full1.samples]
        elev_values1 = [round(s.elevation_deg, 2) for s in full1.samples]
        elev_values2 = [round(s.elevation_deg, 2) for s in full2.samples]

        # 单端 AER（仰角 ≥ 各自最低仰角）
        aero1_all = [
            {"time": s.time, "az": round(s.azimuth_deg, 2), "el": round(s.elevation_deg, 2), "range": round(s.range_km, 1)}
            for s in full1.samples if s.elevation_deg >= p1_min_el
        ]
        aero2_all = [
            {"time": s.time, "az": round(s.azimuth_deg, 2), "el": round(s.elevation_deg, 2), "range": round(s.range_km, 1)}
            for s in full2.samples if s.elevation_deg >= p2_min_el
        ]
        # 两地通信 AER（两端仰角同时 ≥ 各自最低仰角）
        aero2_map = {s.time: s for s in full2.samples}
        comm_all = []
        for s1 in full1.samples:
            s2 = aero2_map.get(s1.time)
            if s2 is None or s1.elevation_deg < p1_min_el or s2.elevation_deg < p2_min_el:
                continue
            comm_all.append({
                "time": s1.time,
                "a_az": round(s1.azimuth_deg, 2), "a_el": round(s1.elevation_deg, 2), "a_range": round(s1.range_km, 1),
                "b_az": round(s2.azimuth_deg, 2), "b_el": round(s2.elevation_deg, 2), "b_range": round(s2.range_km, 1),
            })

        ssc = OPTIONS["卫星"]["SSC"]
        day = start_date.isoformat()
        pdf_error = ""

        def _comm_cols():
            return ["时间（北京时间）", f"{p1_label}方位角(°)", f"{p1_label}仰角(°)", f"{p1_label}距离(km)",
                    f"{p2_label}方位角(°)", f"{p2_label}仰角(°)", f"{p2_label}距离(km)"]

        def _single_cols():
            return ["时间（北京时间）", "方位角(°)", "仰角(°)", "距离(km)"]

        def _comm_row(r):
            return [r["time"], str(r["a_az"]), str(r["a_el"]), str(r["a_range"]),
                    str(r["b_az"]), str(r["b_el"]), str(r["b_range"])]

        def _single_row(r):
            return [r["time"], str(r["az"]), str(r["el"]), str(r["range"])]

        def _win_pdf(code, rows, kind, win_no, plat, plon, start_str, stop_str, label):
            nonlocal pdf_error
            if kind == "comm":
                aer_table = [_comm_cols()] + [_comm_row(r) for r in rows]
                hdr = (f"{p1_label}：{_geo_text(p1_lat, p1_lon)}<br/>"
                       f"{p2_label}：{_geo_text(p2_lat, p2_lon)}<br/>"
                       f"仿真时间 {day}<br/>通信时间 {start_str[11:19]} ~ {stop_str[11:19]}<br/>"
                       f"最新星历：{tle.get('epoch_local', '—')}")
            else:
                aer_table = [_single_cols()] + [_single_row(r) for r in rows]
                hdr = (f"{label}：{_geo_text(plat, plon)}<br/>"
                       f"仿真时间 {day}<br/>可用时间 {start_str[11:19]} ~ {stop_str[11:19]}<br/>"
                       f"最新星历：{tle.get('epoch_local', '—')}")
            try:
                return _store_export(f"AER_{ssc}_{day}_{code}_W{win_no}.pdf",
                                     _build_pdf_report({"header": hdr, "aer": aer_table}),
                                     "application/pdf")
            except Exception as exc:  # noqa: BLE001
                pdf_error = f"PDF 生成失败：{exc}"
                return ""

        def _merged_pdf(code, entries, kind, plat, plon, group):
            """合并全部窗口：每个窗口一个 section，强制新起一页，窗口之间不混排。"""
            nonlocal pdf_error
            try:
                sections = []
                for idx, e in enumerate(entries):
                    if kind == "comm":
                        rows_t = [_comm_cols()] + [_comm_row(r) for r in e["rows"]]
                        full_hdr = (f"{p1_label}：{_geo_text(p1_lat, p1_lon)}<br/>"
                                    f"{p2_label}：{_geo_text(p2_lat, p2_lon)}<br/>"
                                    f"仿真时间 {day}<br/>最新星历：{tle.get('epoch_local', '—')}")
                    else:
                        rows_t = [_single_cols()] + [_single_row(r) for r in e["rows"]]
                        full_hdr = (f"{group}：{_geo_text(plat, plon)}<br/>"
                                    f"仿真时间 {day}<br/>最新星历：{tle.get('epoch_local', '—')}")
                    sections.append({
                        "title": (f"窗口 {e['no']}　可用时间 "
                                  f"{e['start'][11:19]} ~ {e['stop'][11:19]}"),
                        "header": full_hdr if idx == 0 else "",
                        "aer": rows_t,
                    })
                return _store_export(f"AER_{ssc}_{day}_{code}_WAll.pdf",
                                     _build_pdf_report({"sections": sections}),
                                     "application/pdf")
            except Exception as exc:  # noqa: BLE001
                pdf_error = f"PDF 生成失败：{exc}"
                return ""

        def _make_entries(code, group, windows, rows_all, kind, plat, plon):
            entries = []
            for w in windows:
                rows = [r for r in rows_all if w.start_time <= r["time"] <= w.stop_time]
                if not rows:
                    continue
                csv_bytes = _aer_comm_csv_bytes(rows, p1_label, p2_label) if kind == "comm" else _aer_csv_bytes(rows)
                entries.append({
                    "no": w.access_number,
                    "win": f"窗口{w.access_number}",
                    "group": group,
                    "kind": kind,
                    "count": len(rows),
                    "rows": rows,
                    "start": w.start_time,
                    "stop": w.stop_time,
                    "csv": _store_export(f"AER_{ssc}_{day}_{code}_W{w.access_number}.csv",
                                         csv_bytes, "text/csv; charset=utf-8"),
                    "pdf": _win_pdf(code, rows, kind, w.access_number, plat, plon, w.start_time, w.stop_time, group),
                })
            # 合并全部窗口：每个窗口单独一页，窗口之间不混排
            if len(entries) >= 2:
                merged_rows = [r for e in entries for r in e["rows"]]
                merged_win = "窗口" + "+".join(str(e["no"]) for e in entries)
                csv_bytes = _aer_comm_csv_bytes(merged_rows, p1_label, p2_label) if kind == "comm" else _aer_csv_bytes(merged_rows)
                merged_entry = {
                    "no": 0,
                    "win": merged_win,
                    "group": group,
                    "kind": kind,
                    "count": len(merged_rows),
                    "rows": merged_rows,
                    "start": entries[0]["start"],
                    "stop": entries[-1]["stop"],
                    "csv": _store_export(f"AER_{ssc}_{day}_{code}_WAll.csv",
                                         csv_bytes, "text/csv; charset=utf-8"),
                }
                merged_entry["pdf"] = _merged_pdf(code, entries, kind, plat, plon, group)
                entries.append(merged_entry)
            return entries

        downloads = (
            _make_entries("P1", p1_label, vis1.access_intervals, aero1_all, "single", p1_lat, p1_lon)
            + _make_entries("P2", p2_label, vis2.access_intervals, aero2_all, "single", p2_lat, p2_lon)
            + _make_entries("COMM", "两地通信", vis_comm.access_intervals, comm_all, "comm", p1_lat, p1_lon)
        )

        def _fmt_windows(intervals):
            return [
                {"number": w.access_number, "start": w.start_time, "stop": w.stop_time,
                 "duration": _format_duration(w.duration_sec), "max_el": f"{w.max_elevation_deg:.1f}",
                 "peak": w.max_elevation_time or "—",
                 "clipped": ("起止截断" if w.clipped_start and w.clipped_stop
                             else ("起点截断" if w.clipped_start else ("终点截断" if w.clipped_stop else "完整")))}
                for w in intervals
            ]

        context.update(
            result={
                "p1": {"label": p1_label, "lat": p1_lat, "lon": p1_lon,
                       "minEl": p1_min_el, "gso": p1_gso,
                       "windows": _fmt_windows(vis1.access_intervals),
                       "count": len(vis1.access_intervals),
                       "total_hours": f"{vis1.total_visible_sec / 3600.0:.1f}"},
                "p2": {"label": p2_label, "lat": p2_lat, "lon": p2_lon,
                       "minEl": p2_min_el, "gso": p2_gso,
                       "windows": _fmt_windows(vis2.access_intervals),
                       "count": len(vis2.access_intervals),
                       "total_hours": f"{vis2.total_visible_sec / 3600.0:.1f}"},
                "comm": {"windows": _fmt_windows(vis_comm.access_intervals),
                         "count": len(vis_comm.access_intervals),
                         "total_hours": f"{vis_comm.total_visible_sec / 3600.0:.1f}"},
                "elev_chart": {"labels": elev_labels, "values1": elev_values1, "values2": elev_values2,
                               "threshold1": p1_min_el, "threshold2": p2_min_el},
                "track": track_points,
                "downloads": downloads,
                "pdfError": pdf_error,
                "stations": {"p1": {"label": p1_label, "lat": p1_lat, "lon": p1_lon, "minEl": p1_min_el, "gsoAvoid": p1_gso},
                             "p2": {"label": p2_label, "lat": p2_lat, "lon": p2_lon, "minEl": p2_min_el, "gsoAvoid": p2_gso}},
            }
        )
    except (ValueError, KeyError) as exc:
        context["error"] = str(exc)
    except Exception as exc:  # noqa: BLE001
        context["error"] = f"计算失败：{exc}"

    return templates.TemplateResponse(request, "visibility.html", context)


@app.get("/download/{token}")
async def download_export(token: str):
    """下载导出文件（CSV / PDF；由最近一次计算生成，令牌缓存最多保留 24 份）。"""
    item = _EXPORTS.get(token)
    if not item:
        return JSONResponse(
            {"ok": False, "message": "下载链接已过期，请重新计算后再下载。"},
            status_code=404,
        )
    filename, content, media_type = item
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/satellite/now")
async def api_satellite_now(
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    alt: float = 0.0,
    min_el: float = 15.0,
    mask: str = "",
    gso_avoid: float = 15.0,
):
    """实时星下点：供世界地图上的「卫星当前位置」与「建链线」轮询。

    传入站点经纬度时，同时返回该站此刻仰角与建链状态（含掩角/干扰约束）。
    """
    tle = _load_tle_record()
    if not tle.get("ok"):
        return JSONResponse({"ok": False, "message": tle.get("message", "TLE 不可用")}, status_code=503)

    station = None
    if lat is not None and lon is not None:
        station = StationConfig(
            name="观测站", latitude_deg=lat, longitude_deg=lon,
            altitude_m=alt, min_elevation_deg=min_el,
            mask=_parse_mask_string(mask),
            gso_avoid_deg=gso_avoid,
        )
    try:
        sub = visibility_service.compute_subpoint(
            tle["line1"], tle["line2"], OPTIONS["卫星"]["名称"],
            datetime.now(timezone.utc), station=station,
        )
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"ok": False, "message": f"计算失败：{exc}"}, status_code=500)
    return {
        "ok": True,
        "lat": round(sub.latitude_deg, 4),
        "lon": round(sub.longitude_deg, 4),
        "altitude_km": round(sub.altitude_km, 1),
        "time": sub.time,
        "elevation_deg": None if sub.elevation_deg is None else round(sub.elevation_deg, 1),
        "linked": sub.linked,
        "gso_sep_deg": None if sub.gso_sep_deg is None else round(sub.gso_sep_deg, 1),
        "block_reason": sub.block_reason,
    }


# --------------------------------------------------------------------------- #
# 试验记录
# --------------------------------------------------------------------------- #
def _parse_time(value: str, default: time) -> time:
    try:
        hour, minute = value.split(":")
        return time(int(hour), int(minute))
    except (ValueError, AttributeError):
        return default


def _draft_from_form(form) -> Dict[str, Any]:
    draft = default_draft()
    try:
        draft["test_date"] = date.fromisoformat(form.get("test_date", ""))
    except (ValueError, TypeError):
        draft["test_date"] = date.today()
    draft["experiment_name"] = str(form.get("experiment_name", "")).strip()
    draft["location_template"] = str(form.get("location_template", OPTIONS["测试地点"][0]))
    draft["location_left"] = str(form.get("location_left", "")).strip()
    draft["location_right"] = str(form.get("location_right", "")).strip()
    draft["location_single"] = str(form.get("location_single", "")).strip()
    draft["start_time"] = _parse_time(form.get("start_time", ""), time(9, 0))
    draft["end_time"] = _parse_time(form.get("end_time", ""), time(10, 0))
    try:
        draft["interruption"] = int(float(form.get("interruption", "0")))
    except (ValueError, TypeError):
        draft["interruption"] = 0
    draft["main_station"] = str(form.get("main_station", OPTIONS["主站"][0]))
    draft["antenna"] = str(form.get("antenna", OPTIONS["小站/天线"][0]))
    draft["baseband"] = str(form.get("baseband", OPTIONS["基带"][0]))
    draft["frequency_template"] = str(form.get("frequency_template", next(iter(OPTIONS["频点模板"]))))
    draft["frequency_text"] = str(form.get("frequency_text", "")).strip() or OPTIONS["频点模板"][draft["frequency_template"]]
    draft["controller"] = str(form.get("controller", OPTIONS["运控人员"][0]))
    draft["participants"] = list(form.getlist("participants"))
    draft["parameters"] = str(form.get("parameters", "")).strip()
    draft["test_description"] = str(form.get("test_description", "")).strip()
    tags = list(form.getlist("problem_tags"))
    custom = str(form.get("custom_tags", "")).strip()
    if custom:
        for tag in custom.replace("，", ",").split(","):
            tag = tag.strip()
            if tag and tag not in tags:
                tags.append(tag)
    draft["problem_tags"] = tags
    draft["problem_description"] = str(form.get("problem_description", "")).strip()
    return draft


def _draft_display(draft: Dict[str, Any]) -> Dict[str, Any]:
    """把 draft 转成模板可直接展示的字符串值。"""
    display = dict(draft)
    display["test_date"] = draft["test_date"].isoformat()
    display["start_time"] = draft["start_time"].strftime("%H:%M")
    display["end_time"] = draft["end_time"].strftime("%H:%M")
    left, right, single = split_location(draft["location_template"])
    display["location_left"] = draft["location_left"] or left
    display["location_right"] = draft["location_right"] or right
    display["location_single"] = draft["location_single"] or single
    return display


@app.get("/records/new", response_class=HTMLResponse)
async def records_new(request: Request):
    draft = default_draft()
    context = _base_context(request, "new", draft=_draft_display(draft),
                            error=None, success=None)
    return templates.TemplateResponse(request, "records_new.html", context)


@app.post("/records/new", response_class=HTMLResponse)
async def records_save(request: Request):
    form = await request.form()
    try:
        draft = _draft_from_form(form)
        record = build_record(draft)
        validate_record(record)
    except (RecordValidationError, ValueError) as exc:
        context = _base_context(request, "new", draft=_draft_display(draft),
                                error=str(exc), success=None)
        return templates.TemplateResponse(request, "records_new.html", context, status_code=400)
    success, message = append_record_to_excel(record)
    if success:
        return RedirectResponse(url=f"/records?flash=success&msg={quote(message)}", status_code=303)
    context = _base_context(request, "new", draft=_draft_display(draft),
                            error=message, success=None)
    return templates.TemplateResponse(request, "records_new.html", context, status_code=400)


@app.get("/records", response_class=HTMLResponse)
async def records_history(request: Request):
    location_filter = request.query_params.get("location", "")
    keyword = request.query_params.get("keyword", "")
    abnormal = request.query_params.get("abnormal", "") == "1"

    try:
        history = load_history()
        read_error = None
    except PermissionError:
        history, read_error = None, PERMISSION_MESSAGE
    except Exception as exc:  # noqa: BLE001
        history, read_error = None, f"读取历史记录失败：{exc}"

    rows: List[Dict[str, Any]] = []
    locations: List[str] = []
    total = 0
    matched = 0
    if history is not None and not history.empty:
        total = len(history)
        locations = list(dict.fromkeys(
            [item for item in OPTIONS["测试地点"] if item != OPTIONS["自定义地点选项"]]
            + [str(v) for v in history["测试地点"].tolist() if str(v).strip()]
        ))
        mask = np.ones(len(history), dtype=bool)
        if location_filter:
            mask &= history["测试地点"].eq(location_filter).to_numpy()
        if keyword:
            mask &= history["问题记录"].str.contains(keyword, case=False, regex=False, na=False).to_numpy()
        if abnormal:
            mask &= ~history["问题记录"].isin(["", "无"]).to_numpy()
        filtered = history.loc[mask].iloc[::-1]
        matched = int(mask.sum())
        columns = ["序号", "测试日期", "测试时间", "测试地点", "运控人员", "问题记录"]
        rows = filtered[columns].astype(str).to_dict("records")

    flash = None
    if request.query_params.get("flash") == "success":
        flash = request.query_params.get("msg", "保存成功")

    context = _base_context(
        request, "records", rows=rows, locations=locations, total=total, matched=matched,
        location_filter=location_filter, keyword=keyword, abnormal=abnormal,
        read_error=read_error, flash=flash,
    )
    return templates.TemplateResponse(request, "records.html", context)


@app.get("/overview", response_class=HTMLResponse)
async def overview(request: Request):
    status = get_excel_status()
    try:
        history = load_history()
    except Exception:  # noqa: BLE001
        history = None

    abnormal_count = 0
    recent: List[Dict[str, Any]] = []
    if history is not None and not history.empty:
        abnormal_mask = ~history["问题记录"].isin(["", "无"])
        abnormal_count = int(abnormal_mask.sum())
        recent = history.iloc[::-1].head(6)[
            ["序号", "测试日期", "测试时间", "测试地点", "运控人员", "问题记录"]
        ].astype(str).to_dict("records")

    context = _base_context(
        request, "overview", status=status, abnormal_count=abnormal_count,
        recent=recent, history=history is not None and not history.empty,
    )
    return templates.TemplateResponse(request, "overview.html", context)
