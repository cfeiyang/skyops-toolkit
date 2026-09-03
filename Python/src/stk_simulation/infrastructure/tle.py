"""CelesTrak TLE 下载、校验和本地缓存。"""

from __future__ import annotations

from pathlib import Path
from time import time
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


def refresh_tle_cache(
    url: str,
    cache_path: str | Path,
    ssc: int,
    timeout: float = 30.0,
    max_cache_age: float = 7200.0,
) -> Path:
    """在线更新指定 SSC 的 TLE；网络失败时使用已有的有效缓存。"""
    path = Path(cache_path)
    if _valid_cache(path, ssc) and time() - path.stat().st_mtime < max_cache_age:
        print(f"[TLE] 使用两小时内的最新缓存: {path}")
        return path
    try:
        content = _download(url, timeout)
        normalized = _normalized_tle(content, ssc)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(f"{path.suffix}.tmp")
        temporary.write_text(normalized, encoding="ascii", newline="\n")
        temporary.replace(path)
        print(f"[TLE] 已从 CelesTrak 更新 SSC={ssc}: {path}")
        return path
    except (OSError, TimeoutError, UnicodeError, URLError, ValueError) as error:
        if _valid_cache(path, ssc):
            print(f"[TLE] 在线更新失败，使用本地缓存: {path}；原因: {error}")
            return path
        raise RuntimeError(
            f"无法从 CelesTrak 获取 SSC={ssc} 的 TLE，且没有有效缓存：{error}"
        ) from error


def _download(url: str, timeout: float) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("TLE 地址必须是有效的 HTTPS URL。")
    request = Request(
        url,
        headers={
            "Accept": "text/plain",
            "User-Agent": "STKSimulation/1.0",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        payload = response.read(65537)
    if len(payload) > 65536:
        raise ValueError("TLE 响应内容异常过大。")
    return payload.decode("ascii")


def _normalized_tle(content: str, ssc: int) -> str:
    """接受 CelesTrak 的三行 TLE，并统一保存为名称行加两行根数。"""
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
        return f"{name}\n{line1}\n{line2}\n"
    raise ValueError(f"响应中没有找到 SSC={ssc} 的标准两行根数。")


def _valid_cache(path: Path, ssc: int) -> bool:
    if not path.is_file():
        return False
    try:
        _normalized_tle(path.read_text(encoding="ascii"), ssc)
    except (OSError, UnicodeError, ValueError):
        return False
    return True
