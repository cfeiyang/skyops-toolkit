function GpsVisibilityApp
%GPSVISIBILITYAPP 单颗目标卫星GPS可见数量独立界面

appDir = fileparts(mfilename('fullpath'));
projectRoot = fileparts(appDir);
addpath(projectRoot);
setupProject(projectRoot);

cfg = configGpsVisibility();
lastResult = [];
root = [];

fig = uifigure('Name', 'GPS可见数量仿真', 'Position', [80 80 1400 760]);
mainGrid = uigridlayout(fig, [1 2]);
mainGrid.ColumnWidth = {500, '1x'};
mainGrid.ColumnSpacing = 10;
mainGrid.Padding = [10 10 10 10];

parameterPanel = uipanel(mainGrid, 'Title', '单星GPS可见性参数', ...
    'FontWeight', 'bold', 'FontSize', 14);
parameterPanel.Layout.Column = 1;
panel = buildGpsVisibilityPanel(parameterPanel, cfg);

resultPanel = uipanel(mainGrid, 'Title', 'GPS可见数量时序图', ...
    'FontWeight', 'bold', 'FontSize', 14);
resultPanel.Layout.Column = 2;
resultGrid = uigridlayout(resultPanel, [2 1]);
resultGrid.RowHeight = {'1x', 40};

ax = uiaxes(resultGrid);
showWaitingState();
saveButton = uibutton(resultGrid, 'push', 'Text', '保存图片', ...
    'FontSize', 13, 'Enable', 'off');

panel.runButton.ButtonPushedFcn = @(~,~) runSimulation();
saveButton.ButtonPushedFcn = @saveImage;

    function runSimulation()
        panel.runButton.Enable = 'off';
        saveButton.Enable = 'off';
        try
            runCfg = panel.readCfg();
            panel.setStatus('状态：正在连接STK...', [0.85 0.45 0]);
            drawnow;
            if isempty(root)
                [~, root] = STKCore.startSTK(runCfg.stk.mode);
            end

            panel.setStatus('状态：正在加载GPS并计算...', [0.85 0.45 0]);
            drawnow;
            lastResult = runGpsVisibility(root, runCfg, ax);
            saveButton.Enable = 'on';
            panel.setStatus(sprintf('状态：完成，图片已保存到 %s', ...
                lastResult.output.imagePath), [0 0.55 0]);
        catch ME
            panel.setStatus('状态：仿真失败', [0.8 0 0]);
            uialert(fig, ME.message, '仿真错误');
        end
        panel.runButton.Enable = 'on';
    end

    function saveImage(~,~)
        if isempty(lastResult)
            uialert(fig, '请先完成仿真。', '保存图片');
            return;
        end

        defaultPath = fullfile(lastResult.output.resultDir, ...
            lastResult.output.imageName);
        [file, path] = uiputfile({'*.png', 'PNG图片 (*.png)'}, ...
            '选择保存目录和文件名', defaultPath);
        if isequal(file, 0)
            return;
        end
        [~, ~, extension] = fileparts(file);
        if isempty(extension)
            file = [file '.png'];
        end

        filePath = fullfile(path, file);
        exportgraphics(ax, filePath, 'Resolution', 300);
        panel.setStatus(sprintf('状态：图片已保存到 %s', filePath), [0 0.4 0]);
    end

    function showWaitingState()
        cla(ax);
        title(ax, '等待仿真');
        text(ax, 0.5, 0.5, '设置参数后点击“开始仿真”', ...
            'Units', 'normalized', 'HorizontalAlignment', 'center', ...
            'FontSize', 14, 'Color', [0.4 0.4 0.4]);
        ax.XTick = [];
        ax.YTick = [];
    end

end
