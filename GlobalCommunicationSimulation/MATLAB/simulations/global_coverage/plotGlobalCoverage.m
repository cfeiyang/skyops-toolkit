function ax = plotGlobalCoverage(result, cfg, ax)
%PLOTGLOBALCOVERAGE 绘制全球通信时长梯度图（只负责可视化，不创建 STK 对象）
%
% 输入：
%   result - runGlobalCoverage 返回的结果（含 coverageData / satellite / scenario）
%   cfg    - 配置（使用 cfg.plot 绘图参数）
%   ax     - 可选：GUI axes；缺省则创建独立 figure
%
% 保留 Behrmann 等面积投影、海岸线、星下轨迹、色标、等值线标注等逻辑。

p = cfg.plot;

%% 逐点通信时长（小时）
covData = result.coverageData;
lat = covData.LatitudeDeg;
lon = covData.LongitudeDeg;
timeHour = covData.TimeHour;

%% 自适应时长色阶
maxHour = max(timeHour, [], 'omitnan');
if ~isfinite(maxHour) || maxHour <= 0
    levelStep = 1;
    maxLevel = 1;
else
    rawStep = maxHour / 8;
    base = 10^floor(log10(rawStep));
    ratio = rawStep / base;
    if ratio <= 1
        niceRatio = 1;
    elseif ratio <= 2
        niceRatio = 2;
    elseif ratio <= 5
        niceRatio = 5;
    else
        niceRatio = 10;
    end
    levelStep = niceRatio * base;
    maxLevel = ceil(maxHour / levelStep) * levelStep;
end

levels = 0:levelStep:maxLevel;
colorLimits = [0 maxLevel];
colorTicks = levels;

%% 经度周期处理
lon = mod(lon, 360);
lonExt = [lon-360; lon; lon+360];
latExt = [lat; lat; lat];
timeExt = [timeHour; timeHour; timeHour];

%% 平滑插值
[lonGrid, latGrid] = meshgrid(p.lonRange(1):p.interpStep:p.lonRange(2), p.latRange(1):p.interpStep:p.latRange(2));
F = scatteredInterpolant(lonExt, latExt, timeExt, 'natural', 'none');
timeGrid = F(lonGrid, latGrid);
timeGrid(timeGrid <= 0) = NaN;

%% 卫星星下轨迹
satLat = cell(size(result.satellites));
satLon = cell(size(result.satellites));
for i = 1:numel(result.satellites)
    [satLat{i}, satLon{i}] = readSatelliteTrack( ...
        result.satellites{i}, result.scenario, p);
end

%% Behrmann 等面积投影
mstruct = defaultm('behrmann');
mstruct.origin = [0 p.centerLon 0];
mstruct = defaultm(mstruct);
[xGrid, yGrid] = projfwd(mstruct, latGrid, lonGrid);
xSat = cell(size(satLat));
ySat = cell(size(satLat));
for i = 1:numel(satLat)
    [xSat{i}, ySat{i}] = projfwd(mstruct, satLat{i}, satLon{i});
end

%% 海岸线
load coastlines coastlat coastlon
coastLat = coastlat;
coastLon = mod(coastlon - p.lonRange(1), 360) + p.lonRange(1);
jump = [false; abs(diff(coastLon)) > 180];
coastLat(jump) = NaN;
coastLon(jump) = NaN;
[xCoast, yCoast] = projfwd(mstruct, coastLat, coastLon);

%% 地面站（启用）
stations = result.cfg.stations([result.cfg.stations.enabled]);
stLat = [stations.lat];
stLon = [stations.lon];
stNames = {stations.name};
[xSt, ySt] = projfwd(mstruct, stLat, stLon);

%% 绘图窗口
standalone = nargin < 3 || isempty(ax);
if standalone
    fig = figure('Color', 'w', 'Position', [100 100 1400 650]);
    ax = axes('Parent', fig, 'Position', [0.08 0.12 0.80 0.78]);
else
    cla(ax);
end

hold(ax, 'on');

%% 通信时长等值填色
[C, h] = contourf(ax, xGrid, yGrid, timeGrid, levels, 'LineColor', [0.25 0.25 0.25], 'LineWidth', 0.5);
colormap(ax, parula(256));
clim(ax, colorLimits);

%% 数据提示（经纬度反投影）
if numel(h.DataTipTemplate.DataTipRows) >= 3
    h.DataTipTemplate.DataTipRows(1) = dataTipTextRow('经度/°', makeSafeDataTipFcn(@(x,y) tipLon(x,y,mstruct)), '%.2f');
    h.DataTipTemplate.DataTipRows(2) = dataTipTextRow('纬度/°', makeSafeDataTipFcn(@(x,y) tipLat(x,y,mstruct)), '%.2f');
    h.DataTipTemplate.DataTipRows(3).Label = '通信时长/h';
    h.DataTipTemplate.DataTipRows(3).Format = '%.2f';
end

%% 等值线数字
if p.showContourLabels && numel(levels) > 1
    clabel(C, h, levels(2:end), 'LabelSpacing', 300, 'Color', 'k', 'FontSize', 9, 'FontWeight', 'bold', 'BackgroundColor', 'none', 'EdgeColor', 'none');
end

%% 海岸线
plot(ax, xCoast, yCoast, 'k', 'LineWidth', 1);

%% 星下轨迹
trackColors = lines(numel(xSat));
for i = 1:numel(xSat)
    plot(ax, xSat{i}, ySat{i}, 'Color', trackColors(i,:), 'LineWidth', 1.3);
end

%% 地面站标记
stationColors = lines(numel(stNames));
for i = 1:numel(stNames)
    plot(ax, xSt(i), ySt(i), 'o', 'MarkerSize', 8, ...
        'MarkerFaceColor', stationColors(i,:), ...
        'MarkerEdgeColor', 'k', 'LineWidth', 1);
    text(ax, xSt(i), ySt(i), [' ' stNames{i}], ...
        'FontSize', 10, 'FontWeight', 'bold', 'Color', 'k', ...
        'HorizontalAlignment', 'left', 'VerticalAlignment', 'middle');
end

%% 经度刻度
[xTicks, ~] = projfwd(mstruct, zeros(size(p.lonTicks)), p.lonTicks);
set(ax, 'XTick', xTicks, 'XTickLabel', p.lonTickLabels);

%% 纬度刻度
[~, yTicks] = projfwd(mstruct, p.latTicks, p.centerLon*ones(size(p.latTicks)));
set(ax, 'YTick', yTicks, 'YTickLabel', p.latTickLabels);

%% 地图范围
[xLim, ~] = projfwd(mstruct, [0 0], p.lonRange);
[~, yLim] = projfwd(mstruct, p.latRange, [p.centerLon p.centerLon]);
xlim(ax, sort(xLim));
ylim(ax, sort(yLim));
axis(ax, 'equal');

%% 坐标轴
box(ax, 'on');
grid(ax, 'on');
ax.GridLineStyle = ':';
ax.GridAlpha = 0.25;
ax.FontSize = 9;
xlabel(ax, '经度/°');
ylabel(ax, '纬度/°');

%% 色标
cb = colorbar(ax, 'eastoutside');
cb.Ticks = colorTicks;
cb.Limits = colorLimits;
cb.Label.String = '通信时长 / h';

if standalone
    cb.Position = [0.90 0.12 0.012 0.78];
end

%% 标题
if isfield(p, 'title') && ~isempty(p.title)
    title(ax, p.title, 'FontWeight', 'normal');
end

hold(ax, 'off');

fprintf('[绘图] 全球通信时长图完成，max = %.3f h, step = %.3f h\n', maxHour, levelStep);

end


%% 读取星下轨迹
function [lat, lon] = readSatelliteTrack(satellite, scenario, p)
lla = satellite.DataProviders.Item('LLA State').Group.Item('Fixed');
data = lla.Exec(scenario.StartTime, scenario.StopTime, p.trackStep);
lat = cell2mat(data.DataSets.GetDataSetByName('Lat').GetValues);
lon = cell2mat(data.DataSets.GetDataSetByName('Lon').GetValues);
lat = lat(:);
lon = mod(lon(:) - p.lonRange(1), 360) + p.lonRange(1);
jump = [false; abs(diff(lon)) > 180];
lat(jump) = NaN;
lon(jump) = NaN;
end


%% 数据提示安全包装
function fcn = makeSafeDataTipFcn(fun)
fcn = @wrapper;
    function value = wrapper(x, y)
        if nargin < 2
            y = x;
        end
        value = fun(x, y);
    end
end


%% 数据提示经度
function lon = tipLon(x, y, mstruct)
[~, lon] = projinv(mstruct, x, y);
lon = mod(lon + 180, 360) - 180;
end


%% 数据提示纬度
function lat = tipLat(x, y, mstruct)
[lat, ~] = projinv(mstruct, x, y);
end
