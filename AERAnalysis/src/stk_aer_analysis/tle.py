"""从 CelesTrak 下载并缓存指定卫星的 TLE。"""

from __future__ import annotations

from dataclasses import dataclass
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


def _download(url: str, timeout: float) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("TLE 地址必须是有效的 HTTPS URL。")
    request = Request(
        url,
        headers={"Accept": "text/plain", "User-Agent": "AERAnalysis/0.1"},
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
