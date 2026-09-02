# 卫星通信仿真工程（Python）

MATLAB 工程 `MATLABFile` 的 Python 移植版。通过 **comtypes** 驱动本机 **STK 12.6** Object Model，业务分层与原工程一致。

## 环境

已用 conda 环境 `stk`（Python 3.10）。依赖：

```text
comtypes  numpy  matplotlib  pandas  scipy
```

激活后运行：

```powershell
conda activate stk
cd D:\Projects\PythonProject\GlobalComSimulation
```

需要本机安装 STK 12（默认路径 `C:\Program Files\AGI\STK 12`）。若安装目录不同，设置环境变量 `STK12_BIN` 指向其 `bin` 目录。

## 目录

```text
app/                    两个独立 GUI（tkinter + matplotlib）
simulations/            正式仿真场景
stk_api/                STK 12.6 COM 公共封装
utils/                  度分秒、Behrmann 投影、海岸线
data/                   TLE、海岸线 npz
results/                PNG 结果
setup_project.py        路径入口
stk_connect.py          连接/启动 STK
```

## 仿真一：全球通信时长

```powershell
python app/global_coverage_app.py
python simulations/global_coverage/run.py
```

多星多站为 ANY OF；多星走星间中继 Chain（地面站 → 上行星 → 下行星）。

## 仿真二：单星 GPS 可见数量

```powershell
python app/gps_visibility_app.py
python simulations/gps_visibility/run.py
```

目标星由 TLE 创建；GPS 用 `LoadGPSConstellation *`；可见定义为到达接收机输入端功率 ≥ 灵敏度。

## 与 MATLAB 的对应关系

| MATLAB | Python |
|---|---|
| `actxserver('STK12.Application')` | `comtypes.client.CreateObject('STK12.Application')` |
| 字符串枚举 `'eSatellite'` | `STKObjects.eSatellite` + `QueryInterface` |
| `table` | `pandas.DataFrame` |
| `scatteredInterpolant` + `projfwd('behrmann')` | `LinearNDInterpolator` + 自实现 Behrmann |
| `uifigure` | tkinter |
| `parula` | matplotlib `viridis`（色标接近，不是同一张 colormap） |

GUI 改参数只影响当次运行，不会写回配置文件。
