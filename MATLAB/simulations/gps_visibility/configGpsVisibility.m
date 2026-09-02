function cfg = configGpsVisibility()

projectRoot = fileparts(fileparts(fileparts(mfilename('fullpath'))));

cfg.paths.repoRoot = projectRoot;
cfg.paths.dataDir = fullfile(projectRoot, 'data');
cfg.paths.resultDir = fullfile(projectRoot, 'results', 'gps_visibility');

cfg.stk.mode = 'new';   % 'new' 新建 STK；'running' 连接已打开的 STK

% 场景时间（文档为完整 24h，改 start 时请同步改 stop）
cfg.scenario.name = 'GPSVisibility';
cfg.scenario.startTime = '1 Sep 2026 00:00:00.000';
cfg.scenario.stopTime = '2 Sep 2026 00:00:00.000';

% 目标卫星：名称、SSC、TLE 路径、传播步长
cfg.satellite.name = 'TN01A';
cfg.satellite.ssc = 59705;
cfg.satellite.step = 60;
cfg.satellite.tleFile = fullfile(cfg.paths.dataDir, 'TN1A_TLE_20260830.txt');

% GPS 链路：发射功率 dBW、L1 频率 MHz
cfg.gps.txPower = 14.28;
cfg.gps.frequency = 1575.42;
cfg.gps.transmitterName = 'GPS_Tx';
cfg.gps.transmitterGroupName = 'GPSTxConstellation';

% 接收机灵敏度 dBW
cfg.receiver.name = 'GPS_Rx';
cfg.receiver.sensitivity = -172;

cfg.chain.name = 'GPSVisibilityChain';
cfg.analysis.step = 60;   % 统计采样步长 / s

cfg.output.imageName = '';
cfg.plot.title = '';

end
