from __future__ import annotations

from stk_api.typelib import instance_name, load_stk_modules, qi


class STKConstraints:
    @staticmethod
    def set_min_elevation(stk_object, min_elevation_deg: float):
        stk_objects, _ = load_stk_modules()
        constraints = stk_object.AccessConstraints
        constraint = qi(
            constraints.AddConstraint(stk_objects.eCstrElevationAngle),
            stk_objects.IAgAccessCnstrMinMax,
        )
        constraint.EnableMin = True
        constraint.Min = min_elevation_deg
        print(f"[约束] {instance_name(stk_object)} 最低仰角 = {min_elevation_deg:.1f} deg")

    @staticmethod
    def set_receiver_sensitivity(receiver, sensitivity: float):
        stk_objects, _ = load_stk_modules()
        constraints = receiver.AccessConstraints
        power_constraint = qi(
            constraints.AddConstraint(stk_objects.eCstrPowerAtReceiverInput),
            stk_objects.IAgAccessCnstrMinMax,
        )
        power_constraint.EnableMin = True
        power_constraint.Min = sensitivity
        print(
            f"[接收机约束] {instance_name(receiver)} "
            f"Power at Receiver Input >= {sensitivity:.3f} dBW"
        )
