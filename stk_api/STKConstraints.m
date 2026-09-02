classdef STKConstraints

methods (Static)

% Minimum Elevation
    function setMinElevation( stkObject, minElevationDeg)

        constraints = stkObject.AccessConstraints;
        constraint = constraints.AddConstraint( 'eCstrElevationAngle');
        constraint.EnableMin = true;
        constraint.Min = minElevationDeg;

        fprintf( '[约束] %s 最低仰角 = %.1f deg\n', stkObject.InstanceName, minElevationDeg);

    end

    function setReceiverSensitivity(receiver, sensitivity)
    
        constraints = receiver.AccessConstraints;
        % 添加 Power at Receiver Input 约束
        powerConstraint = constraints.AddConstraint('eCstrPowerAtReceiverInput');
        % 启用最小值
        powerConstraint.EnableMin = true;
        % 设置接收灵敏度
        powerConstraint.Min = sensitivity;
        fprintf( '[接收机约束] %s Power at Receiver Input >= %.3f dBW\n', receiver.InstanceName, sensitivity);
    end

end

end