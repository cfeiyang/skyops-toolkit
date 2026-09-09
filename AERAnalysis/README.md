# STK 可见性与 AER 分析

本项目使用 Python 3.10、STK Desktop 12.6 和官方 `agi.stk12` API。当前阶段可以自动获取 01A 最新 TLE，并在新建或正在运行的 STK 中创建场景、卫星和地面站。

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
