# 卫星通信仿真工程

基于 MATLAB 与 STK 12.6 COM Object Model 的卫星通信仿真工程。

## 目录

```text
app/            两个独立GUI及其参数面板
simulations/    正式仿真场景
stk_api/        可复用的STK 12.6公共封装
utils/          MATLAB通用工具
data/           TLE等输入数据
results/        图片结果
setupProject.m  路径入口
仿真场景.docx   场景需求
```

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

公共封装按职责划分为 `STKCore / STKObjects / STKConstraints / STKChain / STKCoverage`。业务参数不进入 `stk_api`，便于后续仿真场景复用。

工程优先使用 Object Model；加载 STK 内置GPS星座时使用对应的 Connect Command。

## 代码约定

- 类名使用 PascalCase，函数和变量使用 lowerCamelCase；
- 配置、执行、绘图和GUI分离；
- STK枚举使用字符串名称，不使用裸数字；
- 路径通过 `mfilename('fullpath')` 和 `fullfile` 构造；
- 结果通过 `result` 结构体和 `table` 返回。
