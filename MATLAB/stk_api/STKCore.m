classdef STKCore
%   [app, root] = STKCore.startSTK('new');

methods (Static)

% 启动 / 连接 STK 12.6
    function [app, root] = startSTK(mode)

        if nargin < 1
            mode = 'new';
        end

        mode = lower(string(mode));

        switch mode

            case 'new'
                fprintf('[STK] 正在新建 STK 12 实例...\n');
                app = actxserver('STK12.Application');
                app.Visible = 1;
                app.UserControl = 1;

            case 'running'
                fprintf('[STK] 正在连接已运行的 STK 12 实例...\n');
                app = actxGetRunningServer('STK12.Application');
                app.Visible = 1;

            otherwise
                error( 'STKCore.startSTK: mode 必须是 "new" 或 "running"，收到：%s', mode);

        end

        root = app.Personality2;
        fprintf('[STK] 对象根 root 获取成功。\n');
    end

%创建场景
    function scenario = createScenario( root, name, startTime, stopTime)

        root.UnitPreferences.Item('AngleUnit').SetCurrentUnit('deg');
        root.UnitPreferences.Item('DistanceUnit').SetCurrentUnit('km');
        root.UnitPreferences.Item('TimeUnit').SetCurrentUnit('sec');
        root.UnitPreferences.Item('DateFormat').SetCurrentUnit('UTCG');
        root.UnitPreferences.Item('FrequencyUnit').SetCurrentUnit('MHz');

        % 已存在场景时先关闭
        if ~isempty(root.CurrentScenario)
            root.CloseScenario();
        end

        % 创建 Scenario
        root.NewScenario(name);
        scenario = root.CurrentScenario;

        % 分析时段
        scenario.SetTimePeriod( startTime, stopTime);

        % 时间回到起点
        root.Rewind();

        fprintf( '[场景] 成功创建 Scenario: %s\n', name);

    end

end

end
