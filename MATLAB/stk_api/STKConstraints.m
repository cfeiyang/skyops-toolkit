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

end

end
