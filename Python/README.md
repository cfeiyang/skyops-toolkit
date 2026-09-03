# STK 全球覆盖通信时长仿真

本项目使用 Python 3.10 和 STK Desktop 12.6 官方 `agi.stk12` API，计算单星/三星与地面站组合下的全球通信覆盖时长。

主要能力：

- 每次仿真自动从 CelesTrak 更新参考星 TLE，并保留本地缓存；
- 场景时间默认读取电脑当天日期，计算当天 00:00 至次日 00:00；
- 三星按参考星 RAAN `+0°/+45°/+90°`、平近点角 `0°/−90°/−180°` 自动生成；
- 三星之间建立两两几何可见链路，用于增加覆盖范围和时长；
- 内置上海临港、喀什、佳木斯、海南、墨西哥五个文档站址；
- 地面站名称、经纬度、高度和最低仰角可以编辑；
- 可选视线太阳干扰规避，默认规避角为 15°；
- 输出全球通信时长图和墨西哥规划站覆盖增量图。
- 时长等值梯度固定为 1 小时，等值线直接显示小时标签。

完整的代码结构、调用链、依赖设计和打包说明见 [项目开发与打包指南](docs/PROJECT_GUIDE.md)。

## 环境要求

- Windows 64 位；
- Python 3.10.x；
- STK Desktop 12.6 及有效许可证；
- STK 12.6 Python API wheel。

## 首次安装

在 `Python/` 目录执行：

```powershell
python -m pip install -r requirements.txt
python -m pip install "C:\Program Files\AGI\STK 12\bin\AgPythonAPI\agi.stk12-12.6.0-py3-none-any.whl"
python -m pip install -e .
```

默认在线数据源：

```text
https://celestrak.org/NORAD/elements/gp.php?CATNR=59705&FORMAT=TLE
```

成功下载后缓存到 `Python/data/TN1A_LATEST.tle`。两小时内重复仿真直接使用缓存，以符合 CelesTrak 的更新频率；缓存超过两小时才再次请求。网络失败时使用上次有效缓存；首次运行既无法联网又没有缓存时，程序会明确报错。`data/` 与 `results/` 不纳入 Git。

## 启动桌面程序

```powershell
stk-simulation
```

也可以执行：

```powershell
python -m stk_simulation
```

## 命令行运行

运行当前界面默认的三星五站方案：

```powershell
stk-simulation-cli
```

运行仿真场景文档规定的全部方案：

```powershell
stk-simulation-cli --document-scenarios
```

连接已经运行的 STK：

```powershell
stk-simulation-cli --stk-mode running
```

## 文档全部方案输出

点击“运行文档全部方案”或使用 `--document-scenarios` 后，依次生成：

```text
results/global_coverage/global_coverage_1sat_1station.png
results/global_coverage/global_coverage_3sat_4domestic.png
results/global_coverage/global_coverage_3sat_5station.png
results/global_coverage/global_coverage_3sat_mexico_increase.png
```

## 生成单文件 EXE

```powershell
python -m pip install -r requirements-build.txt
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```

生成文件：

```text
Python/dist/STKSimulation.exe
```

目标电脑不需要安装 Python，但仍需安装并授权 STK Desktop 12.6。程序在线更新 TLE 并缓存到 EXE 同级 `data/`，结果写入 EXE 同级 `results/`。
