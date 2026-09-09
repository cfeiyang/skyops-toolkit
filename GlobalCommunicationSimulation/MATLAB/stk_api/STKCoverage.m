classdef STKCoverage
%STKCOVERAGE Coverage Definition / Grid Seed / FOM 操作

methods (Static)

% Coverage Grid Seed
    function seedFacility = createCoverageGridSeed( scenario, name, minElevationDeg)

        seedFacility = STKObjects.createFacility( scenario, name, 0, 0, 0);
        STKConstraints.setMinElevation( seedFacility, minElevationDeg);
        fprintf( '[覆盖] Grid Seed: %s, min elevation = %.1f deg\n', name, minElevationDeg);

    end

% Global Coverage
    function coverage = createGlobalCoverage( scenario, name, resolutionDeg, chain, gridSeed)
 
        coverage = scenario.Children.New( 'eCoverageDefinition', name);

        % 全球区域
        coverage.Grid.BoundsType = 'eBoundsGlobal';

        %网格分辨率
        coverage.Grid.Resolution.LatLon = resolutionDeg;

        %Grid Point 使用 Facility 模板
        coverage.PointDefinition.GridClass = 'eGridClassFacility';

        coverage.PointDefinition.UseGridSeed = true;

        coverage.PointDefinition.SeedInstance = ['Facility/' gridSeed.InstanceName];

        % Chain 作为 Coverage Asset
        coverage.AssetList.Add( ['Chain/' chain.InstanceName]);

        % 隐藏大量 Grid Point 图标
        coverage.Graphics.Static.IsPointsVisible = false;

        % 计算 Coverage
        coverage.ComputeAccesses();

        fprintf( '[覆盖] Coverage computed: %s, %.2f deg, grid seed = %s\n', name, resolutionDeg, gridSeed.InstanceName);

    end

% Coverage Time FOM
    function fom = createCoverageTimeFOM( coverage, name, minAssets)

        fom = coverage.Children.New( 'eFigureOfMerit', name);
        fom.SetDefinitionType( 'eFmCoverageTime');
        fom.Definition.SetComputeType( 'eTotalTimeAbove');
        fom.Definition.Compute.MinAssets = minAssets;
        fprintf( '[品质因数] Coverage Time created: %s\n', name);

    end

% Read Coverage Time
    function data = readCoverageTime(fom)

        dp = fom.DataProviders.Item( 'Value By Point').Exec;
        lat = cell2mat( dp.DataSets.GetDataSetByName( 'Latitude').GetValues);
        lon = cell2mat( dp.DataSets.GetDataSetByName( 'Longitude').GetValues);
        timeValue = cell2mat( dp.DataSets.GetDataSetByName( 'FOM Value').GetValues);

        lat = lat(:);
        lon = lon(:);
        timeSec = timeValue(:);
        data = table( lat, lon, timeSec, timeSec / 3600, 'VariableNames', { 'LatitudeDeg', 'LongitudeDeg', 'TimeSec', 'TimeHour' });

    end

end

end