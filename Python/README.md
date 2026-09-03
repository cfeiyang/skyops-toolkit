# STK 卫星通信仿真（Python 3.10 / STK 12.6）

这是同级 `MATLAB/` 工程的 Python 实现，使用 STK 12.6 官方
`agi.stk12` API。一个桌面程序统一提供以下功能：

- 全球通信时长分析；
- GPS 可见数量分析。

## 运行环境

- Windows 64 位；
- Python 3.10.x（不要使用 3.10.0）；
- STK Desktop 12.6 及有效许可证；
- STK 12.6 Python API wheel。

## 首次安装

在 `Python/` 目录执行：

```powershell
python -m pip install -r requirements.txt
python -m pip install "C:\Program Files\AGI\STK 12\bin\AgPythonAPI\agi.stk12-12.6.0-py3-none-any.whl"
python -m pip install -e .
```

默认 TLE 文件位置：

```text
Python/data/TN1A_TLE_20260830.txt
```

`data/` 与 `results/` 不纳入 Git。GPS 功能也可以在界面中选择其他 TLE
文件。

## 启动统一桌面程序

```powershell
python -m stk_simulation
```

也可以使用安装后生成的命令：

```powershell
stk-simulation
```

## 命令行运行

```powershell
python -m stk_simulation.cli global-coverage
python -m stk_simulation.cli gps-visibility
```

连接已经运行的 STK：

```powershell
python -m stk_simulation.cli global-coverage --stk-mode running
```

## 生成单文件 EXE

先安装构建依赖：

```powershell
python -m pip install -r requirements-build.txt
```

然后执行：

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```

生成文件：

```text
Python/dist/STKSimulation.exe
```

目标电脑不需要安装 Python，但仍需要安装并授权 STK Desktop 12.6。TLE
文件放在 EXE 同级的 `data/` 目录；结果写入 EXE 同级的 `results/` 目录。

## 工程结构

```text
src/stk_simulation/
├── __main__.py                 统一 GUI 入口
├── cli.py                      统一命令行入口
├── app/
│   ├── main_window.py          主窗口与功能导航
│   ├── simulation_controller.py STK 固定工作线程
│   ├── pages/                  两个功能页面
│   ├── dialogs/                地面站编辑对话框
│   └── widgets/                Matplotlib 结果视图
├── simulations/                配置、计算流程和绘图
├── stk/                        STK 12.6 Object Model 公共封装
├── infrastructure/             运行路径
└── utils/                      通用数值和绘图工具

packaging/
├── stk_simulation.spec         PyInstaller 构建配置
└── build.ps1                   Windows 构建入口
```

所有 STK 对象都在同一个长期工作线程中创建和使用；Qt 主线程只负责界面
显示。新增功能时，在 `simulations/` 增加业务模块、在 `app/pages/` 增加功能
页，并在 `feature_registry.py` 注册。
