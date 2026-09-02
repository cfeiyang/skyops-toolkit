function cfg = configGlobalCoverage()


projectRoot = fileparts(fileparts(fileparts(mfilename('fullpath'))));

cfg.paths.repoRoot  = projectRoot;
cfg.paths.dataDir   = fullfile(projectRoot, 'data');
cfg.paths.resultDir = fullfile(projectRoot, 'results', 'global_coverage');

cfg.stk.mode = 'new';   % 'new' 新建 STK；'running' 连接已打开的 STK

cfg.scenario.name      = 'GlobalCoverage';
cfg.scenario.startTime = '1 Sep 2026 00:00:00.000';
cfg.scenario.stopTime  = '2 Sep 2026 00:00:00.000';

% 单星 TLE（satelliteGroup.mode='single' 时用）
cfg.satellite.name    = 'TN01A';
cfg.satellite.ssc     = 59705;
cfg.satellite.step    = 60;
cfg.satellite.tleFile = fullfile(cfg.paths.dataDir, 'TN1A_TLE_20260830.txt');

% 'single'/'multi'：多星走 satelliteTemplate.m
cfg.satelliteGroup.mode = 'single';
cfg.satelliteGroup.name = 'SatelliteGroup';

% 'single'/'two'/'three'/'four'：站址模板见 stationTemplate.m
cfg.stations = stationTemplate('single');

cfg.groundGroup.name = 'GroundStations';
cfg.chain.name       = 'CommChain';

% Coverage 网格：分辨率 °、网格最低仰角 °
cfg.coverage.name         = 'GlobalCoverage';
cfg.coverage.resolution   = 0.5;
cfg.coverage.minElevation = 15;
cfg.coverage.gridSeedName = 'CoverageGridSeed';

cfg.fom.name      = 'CommunicationTime';
cfg.fom.minAssets = 1;   % ANY OF：至少 1 条路径即可

cfg.output.imageName = '';

cfg.plot = plotDefaults();
cfg.plot.title = '';

end


function p = plotDefaults()
% 改经纬度显示范围、中心经度、色标插值步长时改这里

p.lonRange   = [-60 300];
p.latRange   = [-90 90];
p.centerLon  = 120;
p.interpStep = 0.25;
p.trackStep  = 60;

p.showContourLabels = true;

p.lonTicks      = [-60 0 60 120 180 240 300];
p.lonTickLabels = {'-60','0','60','120','180','-120','-60'};
p.latTicks      = -80:20:80;
p.latTickLabels = {'-80','-60','-40','-20','0','20','40','60','80'};

p.title = '';

end
