"""STK Data Provider 返回值转换工具。"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import numpy as np


def dataset_values(provider_result: Any, dataset_name: str) -> list[Any]:
    values = provider_result.DataSets.GetDataSetByName(dataset_name).GetValues()
    if values is None:
        return []
    if isinstance(values, (str, bytes)):
        return [values]
    if isinstance(values, Iterable):
        return list(values)
    return [values]


def numeric_dataset(provider_result: Any, dataset_name: str) -> np.ndarray:
    converted: list[float] = []
    for value in dataset_values(provider_result, dataset_name):
        if isinstance(value, (list, tuple)) and len(value) == 1:
            value = value[0]
        converted.append(np.nan if value is None else float(value))
    return np.asarray(converted, dtype=float)


def instance_name(stk_object: Any) -> str:
    return str(stk_object.InstanceName)
