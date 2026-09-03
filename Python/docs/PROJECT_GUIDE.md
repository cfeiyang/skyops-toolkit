# STK 全球覆盖通信时长项目开发与打包指南

本文面向第一次接触本项目的开发和维护人员，说明项目的代码层级、全球覆盖计算流程、三星几何星间中继、依赖设计、源码安装和单文件 EXE 打包。

当前产品只实现全球覆盖通信时长。

## 1. 项目运行环境

- Windows 64 位；
- Python 3.10.x；
- STK Desktop 12.6；
- 与 STK 12.6 一致的 `agi.stk12` Python API；
- 有效的 STK 许可证及当前场景使用的 Coverage 等模块许可。

## 2. 一句话理解代码

界面收集参数，仿真服务组织业务流程，`stk/` 封装 STK 12.6 Object Model，计算结果转换成 Pandas/NumPy 数据后交给 Matplotlib 绘图。

```text
PySide6 界面 / CLI
        │
        ▼
GlobalCoverageConfig
        │
        ▼
global_coverage/service.py
        │
        ├────► stk/session.py
        ├────► stk/objects.py
        ├────► stk/constraints.py
        ├────► stk/chain.py
        └────► stk/coverage.py
        │
        ▼
GlobalCoverageResult
        │
        ▼
global_coverage/plot.py ────► GUI 图像和 PNG
```

## 3. 推荐阅读顺序

1. `pyproject.toml`：项目名称、Python 版本、依赖和命令入口。
2. `src/stk_simulation/__main__.py`：桌面程序入口。
3. `app/main_window.py`：窗口、STK 连接模式和页面接线。
4. `app/pages/global_coverage_page.py`：全部可配置参数。
5. `app/simulation_controller.py`：STK 固定工作线程。
6. `simulations/global_coverage/config.py`：默认配置。
7. `simulations/global_coverage/presets.py`：站址和三星轨道派生。
8. `simulations/global_coverage/service.py`：完整计算顺序。
9. `stk/`：底层 STK API 调用。
10. `simulations/global_coverage/plot.py`：结果绘图。

## 4. 完整目录结构

```text
Python/
├── data/                                  输入数据，不提交 Git
│   └── TN1A_TLE_20260830.txt              默认参考星 TLE
├── results/                               运行结果，不提交 Git
│   └── global_coverage/
├── docs/
│   └── PROJECT_GUIDE.md                   本文档
├── packaging/
│   ├── build.ps1                          Windows 构建入口
│   └── stk_simulation.spec                PyInstaller 配置
├── src/stk_simulation/
│   ├── __init__.py                        Python 包标识
│   ├── __main__.py                        GUI 模块入口
│   ├── cli.py                             命令行入口
│   ├── app/
│   │   ├── application.py                 QApplication、字体和样式
│   │   ├── main_window.py                 单功能主窗口
│   │   ├── simulation_controller.py       STK 固定工作线程
│   │   ├── dialogs/station_dialog.py      地面站新增/编辑
│   │   ├── pages/global_coverage_page.py  全球覆盖参数页
│   │   └── widgets/plot_widget.py         Matplotlib 图像区域
│   ├── infrastructure/
│   │   └── paths.py                       源码/EXE 路径规则
│   ├── simulations/
│   │   ├── common.py                      公共配置和输出类型
│   │   └── global_coverage/
│   │       ├── config.py                  默认配置
│   │       ├── presets.py                 文档站址、TLE 解析和三星派生
│   │       ├── service.py                 计算、批量方案和对比
│   │       └── plot.py                    全球通信时长图
│   ├── stk/
│   │   ├── session.py                     STK 会话和 Scenario
│   │   ├── objects.py                     Satellite/Facility/Constellation
│   │   ├── constraints.py                 仰角和太阳排除角
│   │   ├── chain.py                       直达链和星间中继链
│   │   ├── coverage.py                    Coverage 与 FOM
│   │   └── data.py                        Data Provider 数据转换
│   └── utils/
│       ├── geo.py                         度分秒转换
│       └── plotting.py                    中文字体、色图和图片保存
├── pyproject.toml                         包元数据和运行依赖
├── requirements.txt                       运行依赖清单
├── requirements-build.txt                 构建依赖清单
└── README.md                               快速使用说明
```

## 5. `src` 目录和 editable 安装

真正的 Python 包位于 `Python/src/stk_simulation/`。这种常见的 `src layout` 可以避免程序从当前目录误导入同名文件，并让源码运行和打包共享同一套包路径。

执行：

```powershell
python -m pip install -e .
```

当前 Python 环境会记录源码目录。此后可以执行：

```powershell
stk-simulation
stk-simulation-cli
python -m stk_simulation
```

`-e` 是 editable 安装。只修改 `src/` 中的 `.py` 文件后，不需要重新安装；修改 `pyproject.toml` 中的依赖、入口、包名或版本后，需要重新执行安装。

## 6. GUI 启动和线程调用链

`pyproject.toml` 注册：

```toml
[project.scripts]
stk-simulation = "stk_simulation.__main__:main"
stk-simulation-cli = "stk_simulation.cli:main"
```

`stk-simulation` 的启动过程：

```text
stk_simulation.__main__.main()
    → 设置 Matplotlib QtAgg 后端
    → application.run_application()
    → 创建 QApplication
    → 创建 MainWindow
    → 创建 GlobalCoveragePage
    → 创建 SimulationController
```

用户点击开始后的调用过程：

```text
GlobalCoveragePage.read_config()
    → run_requested(config, document_scenarios)
    → MainWindow._start()
    → SimulationController.start()
    → STKWorker.run()（固定 QThread）
    → compute_global_coverage() 或 run_document_scenarios()
    → completed(result)
    → 页面在 Qt 主线程绘图并显示
```

STK 会话在工作线程中延迟创建并复用。Qt 主线程不直接持有 STK Root、Scenario 或其他 STK 对象，避免耗时计算阻塞界面，也避免 STK 对象跨线程使用。

## 7. 默认仿真配置

应用默认加载 Word 仿真场景中的最终方案：

- 仿真时间：`1 Sep 2026 00:00:00.000` 至 `2 Sep 2026 00:00:00.000`；
- 参考星：TN01A，SSC 59705；
- 参考星传播：SGP4，步长 60 s；
- 卫星模式：三星几何星间中继；
- 地面站：四个国内基本站加墨西哥规划站；
- 地面站和全球网格最低仰角：15°；
- Coverage 分辨率：0.5°；
- 太阳干扰规避：默认关闭；
- 规避角预设：15°。

GUI 可以修改场景时间、TLE、SSC、传播步长、卫星模式、Coverage 参数、规避开关和全部地面站参数。

## 8. 文档规定的五个地面站

| 名称 | 分类 | 经度 | 纬度 | 最低仰角 |
|---|---|---:|---:|---:|
| LinGang | 国内基本站 | 121.91944° | 30.9036° | 15° |
| KaShi | 国内基本站 | 76.5128° | 39.7730° | 15° |
| JiaMuSi | 国内基本站 | 134.05789° | 47.99556° | 15° |
| HaiNan | 国内基本站 | 109.57° | 19.94° | 15° |
| Mexico | 海外规划站 | −102.05° | 23.39° | 15° |

预设分为：

- `single`：仅上海临港；
- `domestic`：四个国内基本站；
- `all`：四个国内基本站加墨西哥规划站。

用户仍然可以通过界面增加、删除或修改站址，表格中的每一行都会参与当前仿真。

## 9. 三星如何从参考星 TLE 生成

单星模式直接调用 STK SGP4 的 `AddSegsFromFile()`，从用户选择的 TLE 中加载 SSC 对应卫星。

三星模式先用同一 TLE 创建参考星，再解析同一个 SSC 的两行根数，并按文档生成第二、第三颗卫星：

| 卫星 | RAAN | 平近点角 M | 其他根数 |
|---|---|---|---|
| TN01A | 参考值 | 参考值 | 来自参考星 TLE |
| TN02A | 参考值 + 45° | 参考值 − 90° | 与参考星相同 |
| TN03A | 参考值 + 90° | 参考值 − 180° | 与参考星相同 |

角度通过模 360° 归一化。这样更换 TLE 或仿真历元后，三星仍从当前参考星实时派生，不依赖旧的硬编码轨道根数。

## 10. 三星几何星间中继

本项目中的“星间通信”只表示几何可见，不计算发射功率、接收灵敏度、天线方向图或链路预算。

三星之间的无向几何关系为：

```text
TN01A ↔ TN02A
TN01A ↔ TN03A
TN02A ↔ TN03A
```

为了让 Coverage 中的路径方向明确，三星模式创建：

- 3 条直达链：`地面站组 → 卫星 A`；
- 6 条有向中继链：`地面站组 → 卫星 A → 卫星 B`，其中 `A != B`。

Coverage 计算时会把全球网格点追加到每条 Chain 的末端，因此实际判断的路径为：

```text
直达：地面站 → 卫星 A → 全球网格点
中继：地面站 → 卫星 A → 卫星 B → 全球网格点
```

FOM 的 `MinAssets=1`，任意一条直达或中继路径成立，该网格点在该时刻即计入覆盖。显式排除 `A == B`，不会把同一颗卫星同时作为星间链路两端。

## 11. 最低仰角和干扰规避

每个地面站具有自己的最低仰角，全球 Coverage Grid Seed 还有独立的网格最低仰角。STK 在计算 Access 时组合路径两端适用的约束。

文档只提供“干扰规避角”，未提供具体干扰发射机、功率或频率。因此项目将其实现为 STK 的 `Line Of Sight - Solar Exclusion Angle` 几何约束：

- 开关关闭：不添加太阳排除角，符合“暂不考虑干扰规避”；
- 开关开启：通信视线与太阳方向的夹角必须不小于用户设置值；
- 默认设置值：15°；
- 约束添加到每个地面站和 Coverage Grid Seed。

这不是通信系统 C/I 分析。如果以后需要指定干扰发射机并计算载干比，应作为新的链路预算功能实现。

实现依据可查阅 STK 官方的 [Access 定义](https://help.agi.com/stk/Content/stk/WhatisAccess.htm) 和 [`AgEAccessConstraints` 枚举](https://help.agi.com/stkdevkit/Content/DocX/STKObjects~Enumerations~AgEAccessConstraints_EN.html)。

## 12. 全球覆盖计算顺序

`compute_global_coverage(root, config)` 依次执行：

1. 设置角度、距离、时间、日期和频率单位。
2. 关闭已有 Scenario，创建当前 Scenario 并设置时间范围。
3. 从 TLE 创建参考星；三星模式继续生成 TN02A 和 TN03A。
4. 创建全部 Facility，添加最低仰角和可选太阳排除角。
5. 多站组合为 GroundStations Constellation，含义为 `ANY OF`。
6. 单星创建一条直达 Chain；三星创建直达链和两两星间中继链。
7. 创建 CoverageGridSeed，添加网格最低仰角和可选太阳排除角。
8. 创建全球 Coverage Definition，把所有 Chain 加入 Asset List。
9. 计算 Coverage Access。
10. 创建 Coverage Time Figure Of Merit，要求最少一条有效资产路径。
11. 从 `Value By Point` Data Provider 读取经纬度和累计时间。
12. 从各卫星 `LLA State/Fixed` Data Provider 读取地面轨迹。
13. 返回 `GlobalCoverageResult`，不把 STK 对象传到 GUI 线程。

结果表包含：

| 列名 | 含义 |
|---|---|
| `LatitudeDeg` | 网格点纬度，单位为度 |
| `LongitudeDeg` | 网格点经度，单位为度 |
| `TimeSec` | 累计通信时长，单位为秒 |
| `TimeHour` | 累计通信时长，单位为小时 |

## 13. 文档全部方案和海外站对比

点击“运行文档全部方案”后依次计算：

1. 单星 + 上海临港；
2. 三星 + 四个国内基本站；
3. 三星 + 五站（含墨西哥）；
4. 五站结果减去四个国内站结果，得到墨西哥规划站带来的通信时长增量。

输出：

```text
results/global_coverage/global_coverage_1sat_1station.png
results/global_coverage/global_coverage_3sat_4domestic.png
results/global_coverage/global_coverage_3sat_5station.png
results/global_coverage/global_coverage_3sat_mexico_increase.png
```

增量图按相同经纬度网格对齐，计算：

```text
IncreaseHour = max(FiveStationHour - DomesticHour, 0)
```

只显示正增量区域，用于观察海外规划站增加的覆盖范围和时长。

## 14. 绘图逻辑

`plot_global_coverage()` 完成：

- 对 0°/360° 周期经度扩展后做线性插值；
- 使用 CEA/Behrmann 等面积世界地图；
- 绘制通信时长填色等值面和等值线；
- 绘制海岸线、三星轨迹和地面站；
- 动态选择易读的色阶步长；
- 普通图显示“通信时长 / h”，对比图显示“通信时长增量 / h”；
- 保存 300 DPI PNG。

GUI 单次结果在 Qt 主线程绘制。文档批量方案使用 `FigureCanvasAgg` 离屏保存，全部完成后再把三星五站结果显示到界面。

## 15. STK 公共封装边界

| 文件 | 主要职责 |
|---|---|
| `session.py` | 启动/连接 STK、持有 Root、创建 Scenario、设置单位 |
| `objects.py` | 创建 Facility、SGP4 Satellite 和 Constellation |
| `constraints.py` | 最低仰角和 LOS Sun Exclusion |
| `chain.py` | 创建普通 Chain、直达链和几何星间中继链 |
| `coverage.py` | Coverage、Grid Seed、FOM 和结果读取 |
| `data.py` | 把 STK Data Provider 返回值转换为 list/NumPy array |

边界规则：

- `stk/` 只放可复用 STK API 动作；
- 场景专用顺序和业务判断放在 `service.py`；
- 页面不直接调用 STK；
- 绘图函数不创建 STK 对象；
- STK 枚举使用 `agi.stk12.stkobjects` 的枚举成员，不写裸数字。

## 16. 路径设计

源码运行：

```text
application_root = Python/
data             = Python/data/
results          = Python/results/global_coverage/
```

EXE 运行：

```text
application_root = STKSimulation.exe 所在目录
data             = EXE同级/data/
results          = EXE同级/results/global_coverage/
```

所有路径都由 `infrastructure/paths.py` 生成，不依赖某台电脑的绝对项目路径，也不依赖 PowerShell 当前目录。

## 17. 依赖设计

### 17.1 外部软件

| 依赖 | 用途 | 运行 EXE 是否需要 |
|---|---|---|
| Windows 64 位 | 当前程序平台 | 是 |
| STK Desktop 12.6 | 轨道、Chain 和 Coverage 计算 | 是 |
| STK 有效许可证 | 使用相应分析模块 | 是 |
| Python 3.10 | 源码运行和构建 | 否 |

### 17.2 STK Python API

wheel 通常位于：

```text
C:\Program Files\AGI\STK 12\bin\AgPythonAPI\agi.stk12-12.6.0-py3-none-any.whl
```

安装：

```powershell
python -m pip install "C:\Program Files\AGI\STK 12\bin\AgPythonAPI\agi.stk12-12.6.0-py3-none-any.whl"
```

它来自本机 STK 安装目录，不作为公共 PyPI 依赖写入 `pyproject.toml`。API 版本必须与 STK Desktop 版本一致。

### 17.3 Python 运行依赖

| 包 | 版本范围 | 用途 |
|---|---|---|
| `numpy` | `>=1.23,<2.0` | 数组、轨迹、周期经度和差值计算 |
| `pandas` | `>=1.5,<3.0` | Coverage 表格、站址对比和网格合并 |
| `scipy` | `>=1.9,<2.0` | 全球散点结果线性插值 |
| `matplotlib` | `>=3.6,<4.0` | GUI 图、离屏图和 PNG |
| `basemap` | `>=1.3.6,<2.0` | 世界投影和海岸线 |
| `PySide6` | `>=6.5,<7.0` | GUI、Signal/Slot 和工作线程 |

这些是代码直接 import 的直接依赖。`pip` 安装时还会自动安装 Qt 组件、Basemap 数据等间接依赖，因此安装日志中出现更多包是正常的。

### 17.4 构建依赖

`requirements-build.txt` 在运行依赖基础上增加 `pyinstaller>=6.0,<7.0`。只有打包电脑需要 PyInstaller。

新增第三方 import 时：

1. 运行依赖同时更新 `pyproject.toml` 和 `requirements.txt`；
2. 构建专用依赖更新 `requirements-build.txt`；
3. 含 DLL、数据文件或动态导入时检查 PyInstaller spec；
4. Python 标准库不要写入 requirements。

## 18. 从零安装

```powershell
conda activate stk
python --version
python -m pip --version
cd D:\Projects\STKSimulation\Python
python -m pip install -r requirements.txt
python -m pip install "C:\Program Files\AGI\STK 12\bin\AgPythonAPI\agi.stk12-12.6.0-py3-none-any.whl"
python -m pip install -e .
stk-simulation
```

确认 `python` 和 `pip` 都属于同一个 `stk` 环境。默认 TLE 放入：

```text
Python/data/TN1A_TLE_20260830.txt
```

如果 `stk-simulation` 尚未被 PowerShell 识别，可直接运行：

```powershell
python -m stk_simulation
```

## 19. Git 更新和重新安装

在 `D:\Projects\STKSimulation\Python` 中执行 `git pull`，仍会更新整个 `STKSimulation` 仓库，因为 Git 会向上查找仓库根目录的 `.git`。

```powershell
git status
git pull
```

| 拉取内容 | 后续操作 |
|---|---|
| 只改 `src/` 中的 `.py` | editable 安装下直接重启 |
| 改 `pyproject.toml` 依赖/入口/版本 | `python -m pip install -e .` |
| 改 `requirements.txt` | `python -m pip install -r requirements.txt` |
| 改 PyInstaller spec | 重新打包 |

## 20. 命令行使用

运行默认三星五站：

```powershell
stk-simulation-cli
```

运行文档全部方案：

```powershell
stk-simulation-cli --document-scenarios
```

连接已打开 STK：

```powershell
stk-simulation-cli --stk-mode running
```

## 21. 单文件 EXE 打包

打包电脑必须安装 Python 3.10、全部运行依赖和 STK 12.6 Python API。

在 `Python/` 目录执行：

```powershell
python -m pip install -r requirements-build.txt
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```

输出：

```text
Python/dist/STKSimulation.exe
```

`stk_simulation.spec` 会：

1. 使用 `src/stk_simulation/__main__.py` 作为入口；
2. 收集 `agi.stk12` 的模块、数据和二进制文件；
3. 收集 `mpl_toolkits.basemap_data`；
4. 排除未使用的 `tkinter`；
5. 以 `console=False` 生成无控制台桌面程序；
6. 不使用 UPX；
7. 生成单个 `STKSimulation.exe`。

内部发布建议：

```text
STKSimulation-1.0.0/
├── STKSimulation.exe
├── data/
│   └── TN1A_TLE_20260830.txt
└── 使用说明.md
```

目标电脑不需要 Python，但必须安装并授权 STK Desktop 12.6，并且发布目录必须具有创建 `results/` 和写入 PNG 的权限。

## 22. 新增其他仿真功能

如果以后重新增加一个独立功能，建议创建：

```text
simulations/new_feature/
├── __init__.py
├── config.py
├── service.py
└── plot.py

app/pages/new_feature_page.py
```

保持三段式接口：

```text
config_*()    创建默认配置
compute_*()   操作 STK，返回纯 Python 结果
render_*()    绘图和保存
```

当功能数量重新达到两个以上时，再恢复功能注册表和左侧导航，不需要提前为单个页面保留多功能框架。

## 23. 命名约定

| 对象 | 约定 | 示例 |
|---|---|---|
| 包、模块、文件 | `lower_snake_case` | `global_coverage_page.py` |
| 函数、方法、变量 | `lower_snake_case` | `compute_global_coverage` |
| 类和 dataclass | `PascalCase` | `GlobalCoverageResult` |
| 常量 | `UPPER_SNAKE_CASE` | `STATION_PRESETS` |
| 内部方法 | 前导下划线 | `_coverage_increase` |
| 命令参数 | 连字符 | `--document-scenarios` |

避免使用 `test1.py`、`new.py`、`final.py` 等无法长期说明职责的文件名。

## 24. 常见问题

### `No module named 'agi.stk12'`

当前 Python 环境未安装 STK 12.6 官方 wheel，或 wheel 安装到了另一个环境。使用当前环境的 `python -m pip` 重新安装。

### `No module named 'mpl_toolkits.basemap'`

运行 `python -m pip install -r requirements.txt`。

### `stk-simulation` 无法识别

先执行 `python -m pip install -e .`，或者使用 `python -m stk_simulation`。同时确认终端已激活正确 Conda 环境。

### TLE 中没有指定 SSC

检查界面 SSC 是否与 TLE 第一行、第二行的卫星编号一致。三星模式必须解析该 TLE，不能只在文件中存在其他卫星。

### `QThread: Destroyed while thread is still running`

优先查看它之前的第一段 Traceback。该信息通常是窗口初始化或退出时发生其他异常后的次生现象。

### 中文方框或 Glyph warning

程序优先加载微软雅黑、黑体和常见 CJK 字体。目标 Windows 电脑应保留系统自带的微软雅黑。

## 25. 长期维护边界

- 页面只读取参数和显示结果，不直接操作 STK；
- STK 会话和对象只在固定工作线程使用；
- `service.py` 负责业务顺序，`stk/` 负责单个 API 动作；
- 绘图代码只接收纯 Python 结果；
- 所有路径经 `PathsConfig` 生成；
- 三星轨道从当前 TLE 派生，不恢复历史硬编码根数；
- 几何星间链路显式排除同星两端；
- `data/`、`results/`、`build/`、`dist/` 和虚拟环境不提交 Git；
- 依赖变更时同时检查源码安装和 PyInstaller 打包配置。
