function p = buildGpsVisibilityPanel(parent, cfg)
%BUILDGPSVISIBILITYPANEL GPS可见数量参数面板

grid = uigridlayout(parent, [13 2]);
grid.ColumnWidth = {125, '1x'};
grid.RowHeight = {34, 34, 34, 34, 34, 34, 34, 34, 34, 34, 34, 44, 28};
grid.Padding = [12 12 12 12];
grid.RowSpacing = 6;

[~, scenarioField] = addTextRow(grid, 1, '场景名称', cfg.scenario.name);
[~, startField] = addTextRow(grid, 2, '开始时间', cfg.scenario.startTime);
[~, stopField] = addTextRow(grid, 3, '结束时间（24h）', cfg.scenario.stopTime);
[~, stkModeField] = addDropdownRow(grid, 4, 'STK连接', ...
    {'新建STK', '连接已运行STK'}, {'new', 'running'}, cfg.stk.mode);
[~, satelliteNameField] = addTextRow(grid, 5, '目标卫星', cfg.satellite.name);

tleLabel = uilabel(grid, 'Text', 'TLE文件');
tleLabel.Layout.Row = 6;
tleLabel.Layout.Column = 1;
tleGrid = uigridlayout(grid, [1 2]);
tleGrid.Layout.Row = 6;
tleGrid.Layout.Column = 2;
tleGrid.ColumnWidth = {'1x', 60};
tleGrid.Padding = [0 0 0 0];
tleGrid.ColumnSpacing = 6;
tleField = uieditfield(tleGrid, 'text', 'Value', cfg.satellite.tleFile);
browseButton = uibutton(tleGrid, 'push', 'Text', '浏览');
browseButton.ButtonPushedFcn = @browseTle;

[~, sscField] = addNumericRow(grid, 7, 'SSC编号', cfg.satellite.ssc);
sscField.Limits = [1 Inf];
[~, satelliteStepField] = addNumericRow(grid, 8, ...
    '卫星传播步长/s', cfg.satellite.step);
satelliteStepField.Limits = [1 Inf];
[~, txPowerField] = addNumericRow(grid, 9, 'GPS发射功率/dBW', cfg.gps.txPower);
[~, sensitivityField] = addNumericRow(grid, 10, ...
    '接收灵敏度/dBW', cfg.receiver.sensitivity);
[~, analysisStepField] = addNumericRow(grid, 11, ...
    '统计采样步长/s', cfg.analysis.step);
analysisStepField.Limits = [1 Inf];

runButton = uibutton(grid, 'push', 'Text', '开始仿真', ...
    'FontSize', 14, 'FontWeight', 'bold');
runButton.Layout.Row = 12;
runButton.Layout.Column = [1 2];
statusLabel = uilabel(grid, 'Text', '状态：就绪', ...
    'HorizontalAlignment', 'center', 'FontWeight', 'bold');
statusLabel.Layout.Row = 13;
statusLabel.Layout.Column = [1 2];

    function browseTle(~,~)
        [file, path] = uigetfile({'*.txt;*.tle', 'TLE文件 (*.txt, *.tle)'}, ...
            '选择目标卫星TLE', tleField.Value);
        if ~isequal(file, 0)
            tleField.Value = fullfile(path, file);
        end
    end

    function c = readCfg()
        c = cfg;
        c.scenario.name = scenarioField.Value;
        c.scenario.startTime = startField.Value;
        c.scenario.stopTime = stopField.Value;
        c.stk.mode = stkModeField.Value;
        c.satellite.name = satelliteNameField.Value;
        c.satellite.tleFile = tleField.Value;
        c.satellite.ssc = sscField.Value;
        c.satellite.step = satelliteStepField.Value;
        c.gps.txPower = txPowerField.Value;
        c.receiver.sensitivity = sensitivityField.Value;
        c.analysis.step = analysisStepField.Value;
    end

    function writeCfg(c)
        cfg = c;
        scenarioField.Value = c.scenario.name;
        startField.Value = c.scenario.startTime;
        stopField.Value = c.scenario.stopTime;
        stkModeField.Value = c.stk.mode;
        satelliteNameField.Value = c.satellite.name;
        tleField.Value = c.satellite.tleFile;
        sscField.Value = c.satellite.ssc;
        satelliteStepField.Value = c.satellite.step;
        txPowerField.Value = c.gps.txPower;
        sensitivityField.Value = c.receiver.sensitivity;
        analysisStepField.Value = c.analysis.step;
    end

    function setStatus(txt, color)
        if nargin < 2
            color = [0 0 0];
        end
        statusLabel.Text = txt;
        statusLabel.FontColor = color;
    end

p.runButton = runButton;
p.readCfg = @readCfg;
p.writeCfg = @writeCfg;
p.setStatus = @setStatus;
p.stkModeField = stkModeField;
p.txPowerField = txPowerField;
p.sensitivityField = sensitivityField;
p.analysisStepField = analysisStepField;

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
