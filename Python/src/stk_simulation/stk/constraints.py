"""STK Access Constraints 封装。"""

from __future__ import annotations

from agi.stk12.stkobjects import AgEAccessConstraints

from stk_simulation.stk.data import instance_name


class STKConstraints:
    @staticmethod
    def set_min_elevation(stk_object, min_elevation_deg: float) -> None:
        constraint = stk_object.AccessConstraints.AddConstraint(
            AgEAccessConstraints.eCstrElevationAngle
        )
        constraint.EnableMin = True
        constraint.Min = min_elevation_deg
        print(
            f"[约束] {instance_name(stk_object)} "
            f"最低仰角 = {min_elevation_deg:.1f} deg"
        )

    @staticmethod
    def set_sun_exclusion(stk_object, angle_deg: float) -> None:
        """设置视线与太阳方向的最小夹角，用于太阳干扰规避。"""
        constraint = stk_object.AccessConstraints.AddConstraint(
            AgEAccessConstraints.eCstrLOSSunExclusion
        )
        constraint.Angle = angle_deg
        print(
            f"[干扰规避] {instance_name(stk_object)} "
            f"LOS Sun Exclusion = {angle_deg:.1f} deg"
        )
