"""从 CelesTrak 获取参考星 TLE，并提供已解析的轨道根数。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import time
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class TLEData:
    """一次在线更新得到的参考星数据。"""

    path: Path
    epoch: float
    mean_motion: float
    eccentricity: float
    inclination: float
    arg_perigee: float
    raan: float
    mean_anomaly: float


def load_latest_tle(
    url: str,
    cache_dir: str | Path,
    ssc: int,
    timeout: float = 30.0,
    max_cache_age: float = 7200.0,
) -> TLEData:
    """获取指定 SSC 的最新 TLE；网络失败时使用已有有效缓存。"""
    path = Path(cache_dir) / f"{ssc}_LATEST.tle"
    cached = _read_cache(path, ssc)
    if cached is not None and time() - path.stat().st_mtime < max_cache_age:
        print(f"[TLE] 使用两小时内的最新缓存: {path}")
        return cached
    try:
        content = _download(url, timeout)
        normalized, tle = _parse_tle(content, ssc, path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(f"{path.suffix}.tmp")
        temporary.write_text(normalized, encoding="ascii", newline="\n")
        temporary.replace(path)
        print(f"[TLE] 已从 CelesTrak 更新 SSC={ssc}: {path}")
        return tle
    except (OSError, TimeoutError, UnicodeError, URLError, ValueError) as error:
        cached = _read_cache(path, ssc)
        if cached is not None:
            print(f"[TLE] 在线更新失败，使用本地缓存: {path}；原因: {error}")
            return cached
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


def _parse_tle(content: str, ssc: int, path: Path) -> tuple[str, TLEData]:
    """校验 CelesTrak 三行 TLE，并同时解析三星派生所需的根数。"""
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
        try:
            tle = TLEData(
                path=path,
                epoch=float(line1[18:32]),
                mean_motion=float(line2[52:63]) * 360.0 / 86400.0,
                eccentricity=float(f"0.{line2[26:33].strip()}"),
                inclination=float(line2[8:16]),
                arg_perigee=float(line2[34:42]),
                raan=float(line2[17:25]),
                mean_anomaly=float(line2[43:51]),
            )
        except (IndexError, ValueError) as error:
            raise ValueError(f"SSC={ssc} 的 TLE 轨道根数格式无效。") from error
        return f"{name}\n{line1}\n{line2}\n", tle
    raise ValueError(f"响应中没有找到 SSC={ssc} 的标准两行根数。")


def _read_cache(path: Path, ssc: int) -> TLEData | None:
    if not path.is_file():
        return None
    try:
        _, tle = _parse_tle(path.read_text(encoding="ascii"), ssc, path)
    except (OSError, UnicodeError, ValueError):
        return None
    return tle
