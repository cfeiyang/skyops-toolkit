classdef STKObjects
%STKOBJECTS STK 业务对象创建
%   Facility  Satellite  ……

methods (Static)

%创建地面站 
    function facility = createFacility( scenario, name, lat, lon, alt)
        facility = scenario.Children.New( 'eFacility', name);
        facility.Position.AssignGeodetic( lat, lon, alt);
        fprintf( '[地面站] 成功创建 Facility: %s\n', name);
    end

% 根据TLE创建卫星
    function satellite = createSatelliteFromTLE( root, scenario, name, ssc, step, tleFile)
        
        if ~isfile(tleFile)
            error( 'TLE 文件不存在：%s', tleFile);
        end

        satellite = scenario.Children.New( 'eSatellite', name);
        satellite.SetPropagatorType( 'ePropagatorSGP4');
        propagator = satellite.Propagator;
        propagator.EphemerisInterval.SetImplicitInterval( root.CurrentScenario.Vgt.EventIntervals.Item( 'AnalysisInterval'));
        propagator.Step = step;
        propagator.CommonTasks.AddSegsFromFile( num2str(ssc), tleFile);
        propagator.Propagate();

        %2D 星下轨迹显示完整 Ephemeris
        passData = satellite.Graphics.PassData;
        groundTrack = passData.GroundTrack;
        groundTrack.SetLeadDataType( 'eDataAll');
        groundTrack.SetTrailSameAsLead;
        fprintf( '[卫星] 成功创建 %s (SGP4, SSC=%d, Object Model)\n', name, ssc);
        fprintf( '[卫星] 2D Ground Track 已设置为完整 Ephemeris 范围\n');

    end
    
% 根据参数创建卫星
    function satellite = createSatelliteFromElements(root, scenario, satCfg)
        % 单位
        root.UnitPreferences.Item('AngleUnit').SetCurrentUnit('deg');
        root.UnitPreferences.Item('TimeUnit').SetCurrentUnit('sec');
        root.UnitPreferences.Item('DateFormat').SetCurrentUnit('UTCG');
    
        % 创建 Satellite
        satellite = scenario.Children.New('eSatellite', satCfg.name);
        satellite.SetPropagatorType('ePropagatorSGP4');
        propagator = satellite.Propagator;
    
        % 使用 Scenario 分析时间
        propagator.EphemerisInterval.SetImplicitInterval(root.CurrentScenario.Vgt.EventIntervals.Item('AnalysisInterval'));
        propagator.Step = satCfg.step;
        propagator.AutoUpdateEnabled = false;
    
        % 创建 SGP4 Segment
        propagator.Segments.SSCNumber = num2str(satCfg.ssc);
        segment = propagator.Segments.AddSeg();
    
        % 轨道参数
        segment.Epoch = satCfg.epoch;
        segment.MeanMotion = satCfg.meanMotion;
        segment.Eccentricity = satCfg.eccentricity;
        segment.Inclination = satCfg.inclination;
        segment.ArgOfPerigee = satCfg.argPerigee;
        segment.RAAN = satCfg.raan;
        segment.MeanAnomaly = satCfg.meanAnomaly;
    
        % 传播
        propagator.Propagate();
    
        % 显示完整星下轨迹
        groundTrack = satellite.Graphics.PassData.GroundTrack;
        groundTrack.SetLeadDataType('eDataAll');
        groundTrack.SetTrailSameAsLead;
    
        fprintf('[卫星] %s 创建成功\n', satCfg.name);
    
    end

%创建地面站，组
    function groundNode = createGroundGroup( scenario, name, facilities)

        if isempty(facilities)
            error( 'STKObjects.createGroundGroup: facilities 不能为空。');
        end


        % 单站
        if numel(facilities) == 1
            groundNode = facilities{1};
            fprintf( '[地面站] 成功创建 Single station: %s\n', groundNode.InstanceName);
            return;
        end


        % 多站 Constellation
        groundNode = scenario.Children.New( 'eConstellation', name);

        for i = 1:numel(facilities)
            groundNode.Objects.AddObject( facilities{i});
        end

        fprintf( '[地面站] 成功创建 %d stations, logic = ANY OF\n', numel(facilities));

    end

%创建星座
    function satelliteNode = createSatelliteGroup(scenario, name, satellites)
    
        if isempty(satellites)
            error('STKObjects.createSatelliteGroup: satellites 不能为空。');
        end
    
        % 单星
        if numel(satellites) == 1
            satelliteNode = satellites{1};
            fprintf('[卫星组] Single satellite: %s\n', satelliteNode.InstanceName);
            return;
        end
    
        % 多星 Constellation
        satelliteNode = scenario.Children.New('eConstellation', name);
        for i = 1:numel(satellites)
            satelliteNode.Objects.AddObject(satellites{i});
        end
    
        fprintf('[卫星组] 成功创建 %d satellites, logic = ANY OF\n', numel(satellites));
    
    end

% 创建通用 Constellation
    function constellation = createConstellation(scenario,name,objects)

        if isempty(objects)
            error('STKObjects.createConstellation: objects 不能为空。');
        end
    
        % 创建 Constellation
        constellation = scenario.Children.New('eConstellation', name);
    
        % 批量加入对象
        for i=1:numel(objects)
            constellation.Objects.AddObject(objects{i});
        end
 
        fprintf( '[星座] 成功创建 Constellation: %s，对象数量=%d\n', name, numel(objects));
    
    end

end

end
