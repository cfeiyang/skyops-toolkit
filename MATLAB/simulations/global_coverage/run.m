clc;
clear;
close all;

%% 路径
curDir = fileparts(mfilename('fullpath'));
projectRoot = fileparts(fileparts(curDir));
addpath(projectRoot);
setupProject(projectRoot);

%% 配置
cfg = configGlobalCoverage();

%% 启动 STK
[app, root] = STKCore.startSTK(cfg.stk.mode);

%% 全球覆盖仿真（内部绘图并保存图片）
result = runGlobalCoverage(root, cfg, []);

%% 结果
fprintf('\n');
fprintf('========================================\n');
fprintf(' GLOBAL COVERAGE\n');
fprintf('========================================\n');

fprintf('卫星数量 = %d\n', numel(result.satellites));
fprintf('地面站数量 = %d\n', numel(result.facilities));
fprintf('最大通信时长 = %.3f h\n', result.summary.maxHour);
fprintf('图片 = %s\n', result.output.imagePath);

fprintf('========================================\n');
