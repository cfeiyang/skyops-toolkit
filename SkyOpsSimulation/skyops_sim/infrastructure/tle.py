"""从 CelesTrak 获取参考星 TLE，并提供已解析的轨道根数。"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile
from time import time
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class TLEData:
    """指定目录号的 TLE 及解析后的轨道根数。"""

    path: Path
    epoch: float
    mean_motion: float
    eccentricity: float
    inclination: float
    arg_perigee: float
    raan: float
    mean_anomaly: float
    line1: str
    line2: str


def default_tle_url(ssc: int) -> str:
    return f"https://celestrak.org/NORAD/elements/gp.php?CATNR={ssc}&FORMAT=TLE"


def read_local_tle(file: str | Path, ssc: int) -> TLEData:
    path = Path(file)
    if not path.is_file():
        raise FileNotFoundError(f"TLE 文件不存在：{path}")
    _, tle = _parse_tle(path.read_text(encoding="utf-8-sig"), ssc, path)
    return tle


def resolve_tle(
    ssc: int, cache_dir: str | Path, *, url: str = "", local_file: str = "",
) -> TLEData:
    if local_file:
        return read_local_tle(local_file, ssc)
    return load_latest_tle(url.replace("{ssc}", str(ssc)) or default_tle_url(ssc), cache_dir, ssc)


def load_latest_tle(
    url: str,
    cache_dir: str | Path,
    ssc: int,
    timeout: float = 30.0,
    max_cache_age: float = 7200.0,
) -> TLEData:
    """获取指定 SSC 的最新 TLE；网络失败时使用已有有效缓存。"""
    extra = "" if url == default_tle_url(ssc) else "_" + sha256(url.encode()).hexdigest()[:10]
    path = Path(cache_dir) / f"{ssc}_LATEST{extra}.tle"
    cached = _read_available_cache(path, ssc)
    if cached is not None:
        try:
            if time() - cached.path.stat().st_mtime < max_cache_age:
                print(f"[TLE] 使用有效期内的本地缓存: {cached.path}")
                return cached
        except OSError:
            pass
    try:
        content = _download(url, timeout)
        normalized, tle = _parse_tle(content, ssc, path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            mode="w", encoding="ascii", newline="\n", dir=path.parent, delete=False,
        ) as stream:
            temporary = Path(stream.name)
            try:
                stream.write(normalized)
                stream.close()
                temporary.replace(path)
            finally:
                stream.close()
                temporary.unlink(missing_ok=True)
        print(f"[TLE] 已在线更新 SSC={ssc}: {path}")
        return tle
    except (OSError, TimeoutError, UnicodeError, URLError, ValueError) as error:
        cached = _read_available_cache(path, ssc)
        if cached is not None:
            print(f"[TLE] 在线更新失败，使用本地缓存: {cached.path}；原因: {error}")
            return cached
        raise RuntimeError(
            f"无法在线获取 SSC={ssc} 的 TLE，且未找到有效缓存。\n"
            f"请检查网络或系统代理，或在右上角「卫星设置」中选用本地 TLE 文件。\n"
            f"缓存位置：{path}\n"
            f"详细原因：{error}"
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
            raise ValueError("TLE 行长度无效。")
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
                line1=line1[:69],
                line2=line2[:69],
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


def _read_available_cache(path: Path, ssc: int) -> TLEData | None:
    cached = _read_cache(path, ssc)
    if cached is not None:
        return cached
    project = path.parent.parent
    if project.name.casefold() == "dist":
        project = project.parent
    if project.name.casefold() == "skyopssimulation":
        legacy = project.parent / "STKSimulation" / "GlobalCommunicationSimulation" / "data"
        return _read_cache(legacy / path.name, ssc)
    return None
