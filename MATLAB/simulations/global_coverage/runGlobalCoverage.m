function result = runGlobalCoverage(root, cfg, ax)

if nargin < 3
    ax = [];
end

scCfg=cfg.scenario;

stations = cfg.stations([cfg.stations.enabled]);

scenario = STKCore.createScenario(root, scCfg.name,scCfg.startTime, scCfg.stopTime);

satellites = createSatellites(root, scenario, cfg);

satelliteNode = STKObjects.createSatelliteGroup(scenario, cfg.satelliteGroup.name, satellites);

facilities = cell(1, numel(stations));
for i = 1:numel(stations)
    s = stations(i);
    facilities{i} = STKObjects.createFacility( ...
        scenario, s.name, s.lat, s.lon, s.alt);
    STKConstraints.setMinElevation(facilities{i}, s.minElevation);
end

groundNode = STKObjects.createGroundGroup(scenario, cfg.groundGroup.name, facilities);

satDownNode = [];
if strcmp(cfg.satelliteGroup.mode, 'single')
    % 单星：单跳 地面站 -> 卫星
    chain = STKChain.createSatGroundChain(scenario, cfg.chain.name, groundNode, satelliteNode);
else
    % 多星（三星）：星间中继 地面站 -> 上行星 -> 星间链路 -> 下行星
    satDownNode = STKObjects.createSatelliteGroup( ...
        scenario, [cfg.satelliteGroup.name '_Down'], satellites);
    chain = STKChain.createSatGroundChainWithISL( ...
        scenario, cfg.chain.name, groundNode, satelliteNode, satDownNode);
end

gridSeed = STKCoverage.createCoverageGridSeed( scenario, cfg.coverage.gridSeedName, cfg.coverage.minElevation);

coverage = STKCoverage.createGlobalCoverage( scenario, cfg.coverage.name, cfg.coverage.resolution, chain, gridSeed);

fom = STKCoverage.createCoverageTimeFOM( coverage, cfg.fom.name, cfg.fom.minAssets);

coverageData = STKCoverage.readCoverageTime(fom);

satelliteNames = cellfun(@(sat) char(sat.InstanceName), satellites, 'UniformOutput', false);

stationNames = {stations.name};

baseName = sprintf('global_coverage_%dsat_%dstation',numel(satellites), numel(stations));
if isempty(cfg.output.imageName)
    cfg.output.imageName = [baseName '.png'];
end

cfg.plot.title = sprintf('%s-%s 全球通信时长 (%d星%d站)', ...
    strjoin(satelliteNames, '/'), strjoin(stationNames, '/'), ...
    numel(satellites), numel(stations));

result.scenario = scenario;
result.satellites = satellites;
result.satelliteNode = satelliteNode;
result.satelliteDownNode = satDownNode;
result.facilities = facilities;
result.groundNode = groundNode;
result.chain = chain;
result.coverageGridSeed = gridSeed;
result.coverage = coverage;
result.fom = fom;
result.coverageData = coverageData;
result.summary.satelliteCount = numel(satellites);
result.summary.stationCount = numel(stations);
result.summary.maxHour = max(coverageData.TimeHour, [], 'omitnan');
result.output.resultDir = cfg.paths.resultDir;
result.output.imageName = cfg.output.imageName;
result.cfg = cfg;

% 绘图（ax 为空时创建独立 figure）
if isempty(ax)
    ax = plotGlobalCoverage(result, cfg, []);
else
    plotGlobalCoverage(result, cfg, ax);
end

% 仅保存图片，不保存 CSV
if ~exist(cfg.paths.resultDir, 'dir')
    mkdir(cfg.paths.resultDir);
end
imagePath = fullfile(cfg.paths.resultDir, cfg.output.imageName);
exportgraphics(ax, imagePath, 'Resolution', 300);
result.output.imagePath = imagePath;
fprintf('[保存] 图片已保存: %s\n', imagePath);

end


function satellites = createSatellites(root, scenario, cfg)
if strcmp(cfg.satelliteGroup.mode, 'single')
    satellite = STKObjects.createSatelliteFromTLE(root, scenario, ...
        cfg.satellite.name, cfg.satellite.ssc, ...
        cfg.satellite.step, cfg.satellite.tleFile);
    satellites = {satellite};
    return;
end

satCfgs = satelliteTemplate(cfg.satelliteGroup.mode);

satellites = cell(1, numel(satCfgs));
for i = 1:numel(satCfgs)
    satellites{i} = STKObjects.createSatelliteFromElements( ...
        root, scenario, satCfgs{i});
end
end
