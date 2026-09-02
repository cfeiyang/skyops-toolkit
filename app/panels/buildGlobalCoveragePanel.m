function p = buildGlobalCoveragePanel(parent, cfg)
%BUILDGLOBALCOVERAGEPANEL 全球通信时长参数面板

grid = uigridlayout(parent, [13 2]);
grid.ColumnWidth = {125, '1x'};
grid.RowHeight = {34, 34, 34, 34, 34, 28, 34, 210, 34, 34, 44, 44, 28};
grid.Padding = [12 12 12 12];
grid.RowSpacing = 6;

[~, scenarioField] = addTextRow(grid, 1, '场景名称', cfg.scenario.name);
[~, startField] = addTextRow(grid, 2, '开始时间', cfg.scenario.startTime);
[~, stopField] = addTextRow(grid, 3, '结束时间', cfg.scenario.stopTime);
[~, stkModeField] = addDropdownRow(grid, 4, 'STK连接', ...
    {'新建STK', '连接已运行STK'}, {'new', 'running'}, cfg.stk.mode);
[~, satelliteField] = addDropdownRow(grid, 5, '卫星方案', ...
    {'单星', '多星'}, {'single', 'multi'}, ...
    cfg.satelliteGroup.mode);

satelliteSummary = uilabel(grid, 'Text', '', 'FontColor', [0.3 0.3 0.3]);
satelliteSummary.Layout.Row = 6;
satelliteSummary.Layout.Column = [1 2];

[~, stationModeField] = addDropdownRow(grid, 7, '地面站方案', ...
    {'单站', '双站', '三站', '四站'}, {'single', 'two', 'three', 'four'}, ...
    countMode(numel(cfg.stations)));

stationTable = uitable(grid);
stationTable.Layout.Row = 8;
stationTable.Layout.Column = [1 2];
stationTable.ColumnName = {'启用', '地面站', '纬度/°', '经度/°', '高度/km', '最低仰角/°'};
stationTable.ColumnFormat = {'logical', 'char', 'numeric', 'numeric', 'numeric', 'numeric'};
stationTable.ColumnEditable = true(1, 6);
stationTable.ColumnWidth = {45, 90, 78, 82, 68, 90};
stationTable.RowName = [];

[~, resolutionField] = addNumericRow(grid, 9, ...
    'Coverage分辨率/°', cfg.coverage.resolution);
resolutionField.Limits = [0.1 10];
[~, minElevField] = addNumericRow(grid, 10, ...
    '网格最低仰角/°', cfg.coverage.minElevation);
minElevField.Limits = [0 90];

runButton = uibutton(grid, 'push', 'Text', '开始仿真', ...
    'FontSize', 14, 'FontWeight', 'bold');
runButton.Layout.Row = 11;
runButton.Layout.Column = [1 2];

autoRunButton = uibutton(grid, 'push', 'Text', '自动仿真全部(1×1~3×3)', ...
    'FontSize', 13, 'FontWeight', 'bold');
autoRunButton.Layout.Row = 12;
autoRunButton.Layout.Column = [1 2];

statusLabel = uilabel(grid, 'Text', '状态：就绪', ...
    'HorizontalAlignment', 'center', 'FontWeight', 'bold');
statusLabel.Layout.Row = 13;
statusLabel.Layout.Column = [1 2];

satelliteField.ValueChangedFcn = @(~,~) updateSatelliteSummary();
stationModeField.ValueChangedFcn = @(~,~) applyStationMode();
writeCfg(cfg);

    function applyStationMode()
        stationTable.Data = stationsToTable(stationTemplate(stationModeField.Value));
    end

    function updateSatelliteSummary()
        satCfgs = satelliteTemplate(satelliteField.Value);
        names = cellfun(@(s) s.name, satCfgs, 'UniformOutput', false);
        satelliteSummary.Text = ['当前卫星：' strjoin(names, '、')];
    end

    function c = readCfg()
        c = cfg;
        c.scenario.name = scenarioField.Value;
        c.scenario.startTime = startField.Value;
        c.scenario.stopTime = stopField.Value;
        c.stk.mode = stkModeField.Value;
        c.satelliteGroup.mode = satelliteField.Value;
        c.stations = tableToStations(stationTable.Data);
        c.coverage.resolution = resolutionField.Value;
        c.coverage.minElevation = minElevField.Value;
    end

    function writeCfg(c)
        cfg = c;
        scenarioField.Value = c.scenario.name;
        startField.Value = c.scenario.startTime;
        stopField.Value = c.scenario.stopTime;
        stkModeField.Value = c.stk.mode;
        satelliteField.Value = c.satelliteGroup.mode;
        stationModeField.Value = countMode(numel(c.stations));
        stationTable.Data = stationsToTable(c.stations);
        resolutionField.Value = c.coverage.resolution;
        minElevField.Value = c.coverage.minElevation;
        updateSatelliteSummary();
    end

    function setStatus(txt, color)
        if nargin < 2
            color = [0 0 0];
        end
        statusLabel.Text = txt;
        statusLabel.FontColor = color;
    end

p.runButton = runButton;
p.runAllButton = autoRunButton;
p.satelliteField = satelliteField;
p.stationModeField = stationModeField;
p.stationTable = stationTable;
p.readCfg = @readCfg;
p.writeCfg = @writeCfg;
p.setStatus = @setStatus;

end


function [label, field] = addTextRow(parent, row, labelText, value)
label = uilabel(parent, 'Text', labelText);
label.Layout.Row = row;
label.Layout.Column = 1;
field = uieditfield(parent, 'text', 'Value', value);
field.Layout.Row = row;
field.Layout.Column = 2;
end


function [label, field] = addNumericRow(parent, row, labelText, value)
label = uilabel(parent, 'Text', labelText);
label.Layout.Row = row;
label.Layout.Column = 1;
field = uieditfield(parent, 'numeric', 'Value', value);
field.Layout.Row = row;
field.Layout.Column = 2;
end


function [label, field] = addDropdownRow(parent, row, labelText, items, itemData, value)
label = uilabel(parent, 'Text', labelText);
label.Layout.Row = row;
label.Layout.Column = 1;
field = uidropdown(parent, 'Items', items, 'ItemsData', itemData, 'Value', value);
field.Layout.Row = row;
field.Layout.Column = 2;
end


function data = stationsToTable(stations)
data = cell(numel(stations), 6);
for i = 1:numel(stations)
    data(i,:) = {stations(i).enabled, stations(i).name, stations(i).lat, ...
        stations(i).lon, stations(i).alt, stations(i).minElevation};
end
end


function stations = tableToStations(data)
stations = struct('name', {}, 'lat', {}, 'lon', {}, 'alt', {}, ...
    'minElevation', {}, 'enabled', {});
for i = 1:size(data, 1)
    stations(i).enabled = logical(data{i,1});
    stations(i).name = char(string(data{i,2}));
    stations(i).lat = data{i,3};
    stations(i).lon = data{i,4};
    stations(i).alt = data{i,5};
    stations(i).minElevation = data{i,6};
end
end


function mode = countMode(count)
modes = {'single', 'two', 'three', 'four'};
mode = modes{min(max(count, 1), 4)};
end
