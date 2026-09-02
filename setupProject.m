function projectRoot = setupProject(projectRoot)
% 加入正式共享代码：
%   app
%   stk_api
%   simulations
%   utils
%

if nargin < 1 || isempty(projectRoot)
    projectRoot = fileparts(mfilename('fullpath'));
end

addpath(projectRoot);

addpath(genpath(fullfile(projectRoot, 'app')));
addpath(genpath(fullfile(projectRoot, 'stk_api')));
addpath(genpath(fullfile(projectRoot, 'simulations')));
addpath(genpath(fullfile(projectRoot, 'utils')));

fprintf('[PATH] 项目共享代码路径已配置：%s\n', projectRoot);

end
