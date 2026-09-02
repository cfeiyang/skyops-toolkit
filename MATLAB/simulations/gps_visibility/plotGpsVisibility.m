function ax = plotGpsVisibility(result, cfg, ax)
%PLOTGPSVISIBILITY 绘制GPS可见数量时序图

standalone = nargin < 3 || isempty(ax);
if standalone
    fig = figure('Color', 'w', 'Position', [100 100 1200 600]);
    ax = axes('Parent', fig);
else
    cla(ax);
end

data = result.gpsCountData;
stairs(ax, data.ElapsedHour, data.GPSCount, ...
    'LineWidth', 1.5, 'Color', [0 0.35 0.75]);
grid(ax, 'on');
box(ax, 'on');
xlabel(ax, '时间 / h');
ylabel(ax, 'GPS卫星数量');

xlim(ax, [0 24]);
xticks(ax, 0:2:24);

yMax = max(1, result.summary.maxCount + 1);
ylim(ax, [0 yMax]);
yticks(ax, 0:yMax);

if isfield(cfg.plot, 'title') && ~isempty(cfg.plot.title)
    title(ax, cfg.plot.title, 'FontWeight', 'normal');
end

fprintf('[绘图] GPS可见数量图完成，范围=%d至%d颗\n', ...
    result.summary.minCount, result.summary.maxCount);

end
