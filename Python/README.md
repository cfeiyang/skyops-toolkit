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

## 界面与执行方式

桌面界面使用 Python 自带的 `tkinter/ttk`，不需要额外安装 Qt。参数区和结果区可拖动调整宽度；结果区提供 Matplotlib 的缩放、平移和图片保存工具栏。STK 计算在固定工作线程执行，窗口在计算期间仍可正常刷新。

全球覆盖界面的地面站页支持添加、编辑和删除任意数量的自定义地面站；单站到四站方案作为快速填充预设保留。表格中的每个地面站都会参与仿真。

计算与绘图相互独立：

- `compute_global_coverage` / `compute_gps_visibility`：只操作 STK 并返回数值结果。
- `render_global_coverage` / `render_gps_visibility`：只负责绘图和保存。
- `run_global_coverage` / `run_gps_visibility`：供命令行使用的完整入口。

## 目录

```text
app/            tkinter/ttk GUI、异步执行和公共界面组件
simulations/    两个仿真的配置、业务流程和绘图
stk_api/        STK 12.6 Object Model 公共封装
utils/          通用数值和绘图工具
setup_project.py  Python 路径入口
```
