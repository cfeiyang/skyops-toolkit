from __future__ import annotations

import os
from functools import lru_cache

DEFAULT_STK_BIN = r"C:\Program Files\AGI\STK 12\bin"


def stk_bin_dir() -> str:
    return os.environ.get("STK12_BIN", DEFAULT_STK_BIN)


@lru_cache(maxsize=1)
def load_stk_modules():
    from comtypes.client import GetModule

    bin_dir = stk_bin_dir()
    GetModule(os.path.join(bin_dir, "AgStkUtil.dll"))
    GetModule(os.path.join(bin_dir, "AgStkObjects.dll"))
    from comtypes.gen import STKObjects, STKUtil

    return STKObjects, STKUtil


def qi(obj, interface):
    if obj is None:
        return None
    return obj.QueryInterface(interface)


def com_list(values) -> list:
    if values is None:
        return []
    return list(values)


def com_float_array(values):
    import numpy as np

    raw = com_list(values)
    if not raw:
        return np.array([], dtype=float)
    out = []
    for item in raw:
        if item is None:
            out.append(np.nan)
        elif isinstance(item, (list, tuple)) and len(item) == 1:
            out.append(float(item[0]))
        else:
            out.append(float(item))
    return np.asarray(out, dtype=float)


def instance_name(obj) -> str:
    return str(obj.InstanceName)
