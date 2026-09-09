# STK 全球覆盖通信时长仿真

Windows 桌面程序，运行环境为 Python 3.10、STK Desktop 12.6 和 STK 12.6 Python API。

## 本地运行

首次配置环境：

```powershell
conda create -n stk python=3.10 -y
conda activate stk
cd D:\Projects\STKSimulation\GlobalCommunicationSimulation\Python
python -m pip install "C:\Program Files\AGI\STK 12\bin\AgPythonAPI\agi.stk12-12.6.0-py3-none-any.whl"
python -m pip install -e .
stk-simulation
```

也可以通过模块启动：

```powershell
python -m stk_simulation
```

更新代码后，在同一环境中执行：

```powershell
git pull
python -m pip install -e .
stk-simulation
```

PyCharm 直接打开 `STKSimulation/GlobalCommunicationSimulation/Python` 目录，并选择 `stk` 环境中的 `python.exe`。程序首次运行需要联网获取 CelesTrak TLE；缓存写入 `data/`，结果写入 `results/`。

## 打包 EXE

打包电脑必须安装并授权 STK Desktop 12.6，同时安装上述 STK Python API。然后在 `Python/` 目录执行：

```powershell
conda activate stk
python -m pip install -e ".[build]"
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```

生成文件：

```text
dist/STKSimulation.exe
```

EXE 已包含 Python 运行时和应用图标。目标电脑不需要安装 Python，但仍需安装并授权 STK Desktop 12.6；运行数据写入 EXE 同级的 `data/` 和 `results/`。
