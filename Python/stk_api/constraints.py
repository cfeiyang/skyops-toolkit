"""STK Access Constraints 封装。"""

from __future__ import annotations

from agi.stk12.stkobjects import AgEAccessConstraints

from stk_api.data import instance_name


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
    def set_receiver_sensitivity(receiver, sensitivity: float) -> None:
        constraint = receiver.AccessConstraints.AddConstraint(
            AgEAccessConstraints.eCstrPowerAtReceiverInput
        )
        constraint.EnableMin = True
        constraint.Min = sensitivity
        print(
            f"[接收机约束] {instance_name(receiver)} "
            f"Power at Receiver Input >= {sensitivity:.3f} dBW"
        )
