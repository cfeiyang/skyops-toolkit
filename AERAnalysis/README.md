# STK 可见性与 AER 分析

本项目使用 Python 3.10、STK Desktop 12.6 和官方 `agi.stk12` API。程序自动获取 01A 最新 TLE，在 STK 中创建场景、卫星和地面站，并按照最低仰角与太阳干扰规避角两项几何约束，计算指定地面站对卫星的可见时段、方位角、仰角和距离。

界面默认提供成都城市参考坐标 `30.572800°N, 104.066800°E, 500 m`，实际使用时可在地面站编辑窗口中替换为设备的精确坐标和海拔。界面按电脑本地时间输入，STK 场景内部采用 `UTCG`；可见时段和 AER 结果单独转换为 `LCLG`（Local Gregorian），国内电脑设置为 UTC+8 时显示北京时间。

## 本地运行

```powershell
conda create -n stk-aer python=3.10 -y
conda activate stk-aer
cd D:\Projects\STKSimulation\AERAnalysis
python -m pip install "C:\Program Files\AGI\STK 12\bin\AgPythonAPI\agi.stk12-12.6.0-py3-none-any.whl"
python -m pip install -e .
stk-aer-analysis
```

也可以执行：

```powershell
python -m stk_aer_analysis
```

## 打包 EXE

首次打包先安装打包依赖：

```powershell
python -m pip install -e ".[build]"
```

执行打包：

```powershell
powershell -ExecutionPolicy Bypass -File .\packaging\build.ps1
```

生成文件位于 `dist\AERAnalysis.exe`。程序窗口和 EXE 均使用 AER 专用图标；运行电脑仍需安装并授权 STK Desktop 12.6。
