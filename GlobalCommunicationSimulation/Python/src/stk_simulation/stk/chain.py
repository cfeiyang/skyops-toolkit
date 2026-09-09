"""STK Chain 创建。"""

from __future__ import annotations

from itertools import permutations
from typing import Any
from agi.stk12.stkobjects import AgESTKObjectType #type:ignore

from stk_simulation.stk.data import instance_name


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
    def create_sat_ground_chain(scenario, name: str, ground_node, satellite):
        chain = STKChain.create_chain(scenario, name, ground_node, satellite)
        print("[建链] Coverage Asset Mode = APPEND (STK 12.6 default)")
        return chain

    @staticmethod
    def create_satellite_network_chains(
        scenario, base_name: str, ground_node, satellites: list[Any]
    ) -> list[Any]:
        """创建三星直达路径和两两几何星间中继路径。"""
        if len(satellites) < 2:
            raise ValueError("星间网络至少需要两颗卫星。")

        chains = [
            STKChain.create_chain(
                scenario,
                f"{base_name}_Direct_{instance_name(satellite)}",
                ground_node,
                satellite,
            )
            for satellite in satellites
        ]
        for sat_up, sat_down in permutations(satellites, 2):
            chains.append(
                STKChain.create_chain(
                    scenario,
                    (
                        f"{base_name}_Relay_{instance_name(sat_up)}"
                        f"_To_{instance_name(sat_down)}"
                    ),
                    ground_node,
                    sat_up,
                    sat_down,
                )
            )
        print(
            f"[星间通信] 已创建 {len(satellites)} 条直达链和 "
            f"{len(satellites) * (len(satellites) - 1)} 条几何中继链"
        )
        return chains
