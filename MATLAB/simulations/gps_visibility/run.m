clc;
clear;
close all;

%% 路径
currentDir = fileparts(mfilename('fullpath'));
projectRoot = fileparts(fileparts(currentDir));
addpath(projectRoot);
setupProject(projectRoot);

%% 仿真
cfg = configGpsVisibility();
[~, root] = STKCore.startSTK(cfg.stk.mode);
result = runGpsVisibility(root, cfg, []);

%% 摘要
fprintf('\n========================================\n');
fprintf(' GPS VISIBILITY\n');
fprintf('========================================\n');
fprintf('GPS卫星总数 = %d\n', result.summary.gpsTotal);
fprintf('最小可见数量 = %d\n', result.summary.minCount);
fprintf('最大可见数量 = %d\n', result.summary.maxCount);
fprintf('平均可见数量 = %.3f\n', result.summary.meanCount);
fprintf('图片 = %s\n', result.output.imagePath);
fprintf('========================================\n');
