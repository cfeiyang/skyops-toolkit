# 卫星通信仿真工程（Python 3.10 / STK 12.6）

这是同级 `MATLAB/` 工程的 Python 实现，使用 STK 12.6 自带的 `agi.stk12` Python API 驱动 STK Desktop。

## 环境

- Windows
- Python 3.10
- STK Desktop 12.6
- STK 12.6 Python API wheel
- NumPy、Pandas、SciPy、Matplotlib、Basemap

先安装普通 Python 依赖：

```powershell
python -m pip install -r requirements.txt
```

STK Python API 需从 STK 12.6 安装目录中的 wheel 安装，典型位置为：

```powershell
python -m pip install "C:\Program Files\AGI\STK 12\bin\AgPythonAPI\agi.stk12-12.6.0-py3-none-any.whl"
```

## 输入数据

默认 TLE 文件位置：

```text
Python/data/TN1A_TLE_20260830.txt
```

`data/` 和 `results/` 不纳入 Git。

## 运行

全球通信时长 GUI：

```powershell
python app/global_coverage_app.py
```

GPS 可见数量 GUI：

```powershell
python app/gps_visibility_app.py
```

命令行执行：

```powershell
python simulations/global_coverage/run.py
python simulations/gps_visibility/run.py
```

## 目录

```text
app/            tkinter GUI 和参数面板
simulations/    两个仿真的配置、业务流程和绘图
stk_api/        STK 12.6 Object Model 公共封装
utils/          通用数值工具
setup_project.py  Python 路径入口
```
