# 卫星通信仿真工程

基于 MATLAB / Python 与 STK 12.6 Object Model 的卫星通信仿真工程。

- `MATLAB/`：已验证的 MATLAB 实现。
- `Python/`：Python 3.10 与 STK 12.6 官方 `agi.stk12` API 实现，两个仿真功能共用一个桌面程序。

## 目录

```text
MATLAB/         MATLAB 实现
Python/         Python 3.10 实现
```

MATLAB 使用前请先进入 `MATLAB/` 并执行 `setupProject`。
Python 的环境与运行说明见 `Python/README.md`；安装后执行
`python -m stk_simulation` 启动统一界面。

## 仿真一：全球通信时长

支持以下任意组合：

- 单星、双星、三星；
- 单站、双站、三站；
- 地面站参数和最低仰角编辑；
- 全球Coverage分辨率和网格最低仰角设置；
- Coverage Time梯度图和PNG图片保存。

多星和多站采用 `ANY OF` 逻辑：任意一条“地面站 → 卫星 → 全球网格点”路径成立时，该网格点计入通信时长。

启动GUI：

```matlab
GlobalCoverageApp
```

命令行运行：

```matlab
setupProject
cfg = configGlobalCoverage();
[app, root] = STKCore.startSTK(cfg.stk.mode);
result = runGlobalCoverage(root, cfg);
plotGlobalCoverage(result, result.cfg);
```

## 仿真二：单星GPS可见数量

目标卫星固定为单颗，通过TLE创建。仿真时长固定为完整24小时。STK按场景时间加载内置GPS星座，为每颗GPS配置相同发射功率的发射机，在目标卫星上配置带接收灵敏度门限的接收机，统计每个采样时刻满足完整链路的GPS数量。

可配置场景时间、目标卫星TLE与SSC、传播步长、GPS发射功率、接收灵敏度和统计采样步长。输出GPS数量阶梯图和PNG图片。

独立GUI：

```matlab
GpsVisibilityApp
```

命令行运行：

```matlab
setupProject
cfg = configGpsVisibility();
[app, root] = STKCore.startSTK(cfg.stk.mode);
result = runGpsVisibility(root, cfg);
plotGpsVisibility(result, result.cfg);
```

## STK 12.6接口

```matlab
app = actxserver('STK12.Application');
app = actxGetRunningServer('STK12.Application');
root = app.Personality2;
```

Python 公共封装位于 `src/stk_simulation/stk/`，按 Session、Objects、
Constraints、Chain 和 Coverage 职责划分。业务参数不进入 STK 接口层，便于
后续仿真场景复用。

工程优先使用 Object Model；加载 STK 内置GPS星座时使用对应的 Connect Command。

## 代码约定

- 类名使用 PascalCase，函数和变量使用 lowerCamelCase；
- 配置、执行、绘图和GUI分离；
- STK枚举使用字符串名称，不使用裸数字；
- 路径通过 `mfilename('fullpath')` 和 `fullfile` 构造；
- 结果通过 `result` 结构体和 `table` 返回。
