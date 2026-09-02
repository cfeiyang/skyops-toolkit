"""地理数值工具。"""

from __future__ import annotations


def dms2dd(degrees: float, minutes: float, seconds: float) -> float:
    """度分秒转十进制度，对应 MATLAB/utils/dms2dd.m。"""
    return degrees + minutes / 60.0 + seconds / 3600.0
