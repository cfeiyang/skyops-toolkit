"""STK Access 过境窗口与 AER (方位角/仰角/距离) 提取封装。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from stk_simulation.simulations.common import parse_stk_time
from stk_simulation.stk.data import dataset_values, numeric_dataset


class STKAccess:
    """封装 STK 12 Object Model 的 GetAccessToObject 与 AER DataProvider。"""

    @staticmethod
    def compute_access_intervals(
        facility_obj: Any, satellite_obj: Any
    ) -> list[tuple[datetime, datetime]]:
        """计算单站对单星的 STK Access 时间窗口列表 (UTC datetime)。"""
        access = facility_obj.GetAccessToObject(satellite_obj)
        access.ComputeAccess()
        provider = access.DataProviders.Item("Access Data")
        result = provider.Exec(
            facility_obj.Root.CurrentScenario.StartTime,
            facility_obj.Root.CurrentScenario.StopTime,
        )
        try:
            starts = dataset_values(result, "Start Time")
            stops = dataset_values(result, "Stop Time")
        except Exception:
            return []
        return [
            (parse_stk_time(str(s)), parse_stk_time(str(e)))
            for s, e in zip(starts, stops)
        ]

    @staticmethod
    def compute_aer_series(
        facility_obj: Any,
        satellite_obj: Any,
        start_utcg: str,
        stop_utcg: str,
        step_sec: float = 60.0,
    ) -> list[dict[str, Any]]:
        """从 STK 提取指定时段内的 AER 采样序列。"""
        access = facility_obj.GetAccessToObject(satellite_obj)
        access.ComputeAccess()
        aer_dp = access.DataProviders.Item("AER Data").Group.Item("Default")
        res = aer_dp.Exec(start_utcg, stop_utcg, float(step_sec))
        try:
            times = dataset_values(res, "Time")
            az = numeric_dataset(res, "Azimuth")
            el = numeric_dataset(res, "Elevation")
            rg = numeric_dataset(res, "Range")
        except Exception:
            return []

        rows: list[dict[str, Any]] = []
        for idx, t_str in enumerate(times):
            rows.append(
                {
                    "dt_utc": parse_stk_time(str(t_str)),
                    "azimuth_deg": float(az[idx]),
                    "elevation_deg": float(el[idx]),
                    "range_km": float(rg[idx]),
                }
            )
        return rows
