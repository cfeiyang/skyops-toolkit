"""TLE 获取与缓存，供可见性计算使用。

优先读取本地缓存；缓存过期时从 CelesTrak 下载最新两行根数；
下载失败时回退缓存（哪怕已过期），完全没有缓存时才报错。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import time
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class TLERecord:
    name: str
    path: Path


def load_latest_tle(
    url: str,
    cache_dir: str | Path,
    ssc: int,
    timeout: float = 30.0,
    max_cache_age: float = 7200.0,
) -> TLERecord:
    """缓存新鲜直接使用；过期则联网更新；联网失败回退缓存，无缓存才报错。"""
    cache_path = Path(cache_dir) / f"{ssc}_LATEST.tle"
    cached = _read_cache(cache_path, ssc)
    if cached and time() - cache_path.stat().st_mtime < max_cache_age:
        return cached

    try:
        content = _download(url, timeout)
        normalized, name = _normalize_tle(content, ssc)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = cache_path.with_suffix(".tle.tmp")
        temporary.write_text(normalized, encoding="ascii", newline="\n")
        temporary.replace(cache_path)
        return TLERecord(name, cache_path)
    except (OSError, TimeoutError, UnicodeError, URLError, ValueError) as error:
        cached = _read_cache(cache_path, ssc)
        if cached:
            return cached
        raise RuntimeError(
            f"无法获取 SSC={ssc} 的 TLE，且没有有效缓存：{error}"
        ) from error


def read_tle(path: str | Path) -> tuple[str, str, str]:
    """读取缓存 TLE 文件，返回（卫星名, 行1, 行2）。"""
    lines = [
        line.strip()
        for line in Path(path).read_text(encoding="ascii").splitlines()
        if line.strip()
    ]
    if len(lines) < 3 or not lines[1].startswith("1 ") or not lines[2].startswith("2 "):
        raise ValueError(f"TLE 文件格式无效：{path}")
    return lines[0], lines[1], lines[2]


def parse_tle_text(text: str) -> tuple[str, str, str]:
    """解析手动上传的两行根数文本，返回（卫星名, 行1, 行2）。

    接受常见 TLE 文本（可带卫星名称行）；无名称行时名称记为「上传 TLE」。
    逐行校验列数与校验和，任何一行不合法都视为无效。
    """
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    for index, line1 in enumerate(lines[:-1]):
        if not line1.startswith("1 ") or len(line1) < 69 or not _checksum_ok(line1):
            continue
        line2 = lines[index + 1]
        if not line2.startswith("2 ") or len(line2) < 69 or not _checksum_ok(line2):
            continue
        name = (
            lines[index - 1].strip()
            if index > 0 and not lines[index - 1].startswith(("1 ", "2 "))
            else "上传 TLE"
        )
        return name, line1, line2
    raise ValueError("未找到有效两行根数：需「1 」行紧跟「2 」行、各 69 列且校验和匹配。")


def _checksum_ok(line: str) -> bool:
    """TLE 校验和：前 68 位数字求和（负号计 1）模 10 应等于第 69 位。"""
    try:
        expected = int(line[68])
    except (IndexError, ValueError):
        return False
    total = 0
    for ch in line[:68]:
        if ch.isdigit():
            total += int(ch)
        elif ch == "-":
            total += 1
    return total % 10 == expected


def parse_epoch(line1: str) -> datetime:
    """解析 TLE 行1的历元（UTC）。第 19-20 列为两位年份，21-32 列为年积日。"""
    year = int(line1[18:20])
    year += 2000 if year < 57 else 1900
    day_of_year = float(line1[20:32])
    return datetime(year, 1, 1, tzinfo=timezone.utc) + timedelta(days=day_of_year - 1.0)


def _download(url: str, timeout: float) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("TLE 地址必须是有效的 HTTPS URL。")
    request = Request(
        url,
        headers={"Accept": "text/plain", "User-Agent": "SkyOps/2.0"},
    )
    with urlopen(request, timeout=timeout) as response:
        payload = response.read(65537)
    if len(payload) > 65536:
        raise ValueError("TLE 响应内容异常过大。")
    return payload.decode("ascii")


def _normalize_tle(content: str, ssc: int) -> tuple[str, str]:
    lines = [line.rstrip() for line in content.splitlines() if line.strip()]
    target = str(ssc)
    for index, line1 in enumerate(lines[:-1]):
        if not line1.startswith("1 ") or line1[2:7].strip() != target:
            continue
        line2 = lines[index + 1]
        if not line2.startswith("2 ") or line2[2:7].strip() != target:
            continue
        if len(line1) < 69 or len(line2) < 69:
            raise ValueError("CelesTrak 返回的 TLE 行长度无效。")
        name = (
            lines[index - 1].strip()
            if index > 0 and not lines[index - 1].startswith(("1 ", "2 "))
            else f"SSC {ssc}"
        )
        return f"{name}\n{line1}\n{line2}\n", name
    raise ValueError(f"响应中没有找到 SSC={ssc} 的标准两行根数。")


def _read_cache(path: Path, ssc: int) -> TLERecord | None:
    if not path.is_file():
        return None
    try:
        _, name = _normalize_tle(path.read_text(encoding="ascii"), ssc)
    except (OSError, UnicodeError, ValueError):
        return None
    return TLERecord(name, path)
