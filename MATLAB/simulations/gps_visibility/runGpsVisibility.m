function result = runGpsVisibility(root, cfg, ax)

if nargin < 3
    ax = [];
end

scCfg=cfg.scenario;saCfg=cfg.satellite;%配置

%创建场景
scenario = STKCore.createScenario(root, scCfg.name, scCfg.startTime, scCfg.stopTime);

%创建卫星
satellite = STKObjects.createSatelliteFromTLE(root, scenario, saCfg.name,saCfg.ssc,saCfg.step, saCfg.tleFile);

%导入STK自带GPS星座
gpsConstellation = STKObjects.loadGpsConstellation(root, scenario);

%取得GPS星数量
gpsSatellites = STKObjects.getGpsSatellites(scenario);

if isempty(gpsSatellites)
    error('GpsVisibility:noGps', 'STK没有加载出可用的GPS卫星。');
end

%根据GPS星数量获得GPS发射机数量
gpsTransmitters = cell(size(gpsSatellites));

%创建发射机
for i = 1:numel(gpsSatellites)
    transmitter = STKObjects.createTransmitter(gpsSatellites{i}, cfg.gps.transmitterName);
    transmitter.Model.Eirp = cfg.gps.txPower;
    transmitter.Model.Frequency = cfg.gps.frequency;
    gpsTransmitters{i} = transmitter;
end
fprintf('[GPS] 已创建%d个发射机，发射功率=%.2f dBW，频率=%.2f MHz\n', numel(gpsTransmitters), cfg.gps.txPower, cfg.gps.frequency);

receiver = STKObjects.createReceiver(satellite, cfg.receiver.name);

STKConstraints.setReceiverSensitivity(receiver, cfg.receiver.sensitivity);

transmitterGroup = STKObjects.createConstellation(scenario, cfg.gps.transmitterGroupName, gpsTransmitters);

chain = STKChain.createChain(scenario, cfg.chain.name, transmitterGroup, receiver);

gpsCountData = STKChain.readNumberOfAccesses( chain, scenario, cfg.analysis.step);
gpsCountData.Properties.VariableNames{'AccessCount'} = 'GPSCount';

baseName = sprintf('gps_visibility_%s', lower(cfg.satellite.name));

if isempty(cfg.output.imageName)
    cfg.output.imageName = [baseName '.png'];
end

cfg.plot.title = sprintf('%s 24小时GPS可见数量', cfg.satellite.name);

result.scenario = scenario;
result.satellite = satellite;
result.gpsConstellation = gpsConstellation;
result.gpsSatellites = gpsSatellites;
result.gpsTransmitters = gpsTransmitters;
result.receiver = receiver;
result.transmitterGroup = transmitterGroup;
result.chain = chain;
result.gpsCountData = gpsCountData;
result.summary.gpsTotal = numel(gpsSatellites);
result.summary.minCount = min(gpsCountData.GPSCount);
result.summary.maxCount = max(gpsCountData.GPSCount);
result.summary.meanCount = mean(gpsCountData.GPSCount);
result.summary.visibleSampleCount = nnz(gpsCountData.GPSCount > 0);
result.summary.sampleCount = height(gpsCountData);
result.output.resultDir = cfg.paths.resultDir;
result.output.imageName = cfg.output.imageName;
result.cfg = cfg;

% 绘图并保存图片
if isempty(ax)
    ax = plotGpsVisibility(result, cfg, []);
else
    plotGpsVisibility(result, cfg, ax);
end
if ~exist(cfg.paths.resultDir, 'dir')
    mkdir(cfg.paths.resultDir);
end
imagePath = fullfile(cfg.paths.resultDir, cfg.output.imageName);
exportgraphics(ax, imagePath, 'Resolution', 300);
result.output.imagePath = imagePath;
fprintf('[保存] 图片已保存: %s\n', imagePath);

end
