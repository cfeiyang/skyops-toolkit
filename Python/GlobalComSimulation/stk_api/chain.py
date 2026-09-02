from __future__ import annotations

import numpy as np
import pandas as pd

from stk_api.typelib import com_float_array, com_list, load_stk_modules, qi


class STKChain:
    @staticmethod
    def create_chain(scenario, name: str, *nodes):
        stk_objects, _ = load_stk_modules()
        if len(nodes) < 2:
            raise ValueError("STKChain.create_chain: Chain 至少需要两个对象。")
        chain = qi(scenario.Children.New(stk_objects.eChain, name), stk_objects.IAgChain)
        for node in nodes:
            chain.Objects.AddObject(node)
        chain.ComputeAccess()
        print(f"[建链] Chain created: {name}，对象数量={len(nodes)}")
        return chain

    @staticmethod
    def create_sat_ground_chain(scenario, name: str, ground_node, satellite):
        chain = STKChain.create_chain(scenario, name, ground_node, satellite)
        print("[建链] Coverage Asset Mode = APPEND (STK 12.6 default)")
        return chain

    @staticmethod
    def create_sat_ground_chain_with_isl(scenario, name: str, ground_node, sat_up_node, sat_down_node):
        chain = STKChain.create_chain(scenario, name, ground_node, sat_up_node, sat_down_node)
        print(f"[建链] Chain created (星间中继): {name}")
        return chain

    @staticmethod
    def read_number_of_accesses(chain, scenario, step: float) -> pd.DataFrame:
        dp = chain.DataProviders.Item("Base Object Data")
        data = dp.Exec(scenario.StartTime, scenario.StopTime, step)
        time = com_list(data.DataSets.GetDataSetByName("Time").GetValues())
        count = com_float_array(data.DataSets.GetDataSetByName("Number Of Accesses").GetValues())
        access_objects = com_list(data.DataSets.GetDataSetByName("Access Objects").GetValues())
        elapsed_hour = np.arange(len(count)) * step / 3600.0
        return pd.DataFrame(
            {
                "Time": time,
                "ElapsedHour": elapsed_hour,
                "AccessCount": count,
                "AccessObjects": access_objects,
            }
        )
