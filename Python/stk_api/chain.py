"""STK Chain 创建与结果读取。"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from agi.stk12.stkobjects import AgESTKObjectType

from stk_api.data import dataset_values, numeric_dataset


class STKChain:
    @staticmethod
    def create_chain(scenario, name: str, *nodes: Any):
        if len(nodes) < 2:
            raise ValueError("STKChain.create_chain: Chain 至少需要两个对象。")

        chain = scenario.Children.New(AgESTKObjectType.eChain, name)
        for node in nodes:
            chain.Objects.AddObject(node)
        chain.ComputeAccess()
        print(f"[建链] Chain created: {name}，对象数量={len(nodes)}")
        return chain

    @staticmethod
    def read_number_of_accesses(chain, scenario, step: float) -> pd.DataFrame:
        provider = chain.DataProviders.Item("Base Object Data")
        result = provider.Exec(scenario.StartTime, scenario.StopTime, step)

        times = dataset_values(result, "Time")
        counts = numeric_dataset(result, "Number Of Accesses")
        access_objects = dataset_values(result, "Access Objects")
        elapsed_hours = np.arange(counts.size, dtype=float) * step / 3600.0

        return pd.DataFrame(
            {
                "Time": times,
                "ElapsedHour": elapsed_hours,
                "AccessCount": counts,
                "AccessObjects": access_objects,
            }
        )

    @staticmethod
    def create_sat_ground_chain(scenario, name: str, ground_node, satellite):
        chain = STKChain.create_chain(scenario, name, ground_node, satellite)
        print("[建链] Coverage Asset Mode = APPEND (STK 12.6 default)")
        return chain

    @staticmethod
    def create_sat_ground_chain_with_isl(
        scenario, name: str, ground_node, sat_up_node, sat_down_node
    ):
        chain = STKChain.create_chain(
            scenario, name, ground_node, sat_up_node, sat_down_node
        )
        print(f"[建链] Chain created (星间中继): {name}")
        return chain
