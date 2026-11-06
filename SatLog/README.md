# SkyOps

卫星试验记录与建链可见性网页工具（原 SatLog）。电脑端双击 `启动 SkyOps.cmd` 即可启动。

基于 **FastAPI + Jinja2** 的深色任务控制台界面，替代原 Streamlit 实现，功能保持不变：

- **建链可见性**：基于 Skyfield SGP4 计算过境可见窗口（对应 STK Access）与 AER（对应 STK AER），支持**掩角 / 干扰规避**（按方位角区间定义遮挡或排除区），输出仰角-时间曲线、极坐标天空图、星下点地面轨迹与可用窗口表。
- **试验记录管理**：新增试验记录、历史问题检索、数据概览，数据存储于 Excel。

## 目录结构

```text
SkyOps/
├─ app/
│  ├─ main.py              FastAPI 入口与路由
│  ├─ config.py            业务配置中心（地点/设备/人员/卫星/掩角）
│  ├─ tle_service.py       TLE 下载、缓存与断网回退
│  ├─ visibility_service.py Skyfield 可见性、AER、掩角与地面轨迹计算
│  ├─ excel_service.py     Excel 读写、样式克隆与并发控制
│  ├─ record_logic.py      地点拼接及录入草稿转记录
│  ├─ paths.py             目录约定
│  ├─ static/css/          深色主题样式
│  └─ templates/           Jinja2 页面模板
├─ data/                   Excel 业务数据与 TLE 缓存
├─ logs/                   uvicorn 与 cpolar 日志
├─ scripts/start_skyops.ps1 启动脚本
├─ requirements.txt        Python 依赖
└─ 启动 SkyOps.cmd         Windows 双击入口
```

## 启动

直接双击 `启动 SkyOps.cmd`。启动窗口需要保持开启；关闭窗口即停止 SkyOps。

启动器会：

1. 自动寻找 `satlog` / `skyops` Conda 环境；
2. 在 `0.0.0.0:8501` 启动 uvicorn；
3. 尝试启动已配置的 cpolar `SkyOps` 隧道；
4. 打开本机浏览器。

本机地址为 <http://localhost:8501>。手机可使用 cpolar 地址；同一局域网内使用 `http://电脑局域网IP:8501`。

## 安装依赖

```powershell
conda activate satlog
python -m pip install -r requirements.txt
```

业务 Excel 位于 `data/试验记录-2026.xlsx`。修改或备份数据时，应优先备份整个 `data/` 目录。

## 掩角 / 干扰规避

过境「末段一段时间不可用、末尾又短暂可用」通常源于天线在某方位角区间被遮挡或存在干扰排除区。在「建链可见性」页的**掩角 / 干扰规避**卡片中，按 `起始方位角 → 结束方位角 → 掩角` 添加区间即可建模；可用条件为：

```
仰角 ≥ max(最低仰角, 掩角(方位角))
```

计算结果会同时反映在仰角-时间曲线（绿=可用、红=遮挡/不可用）、极坐标天空图与可用窗口表中，末段短暂可用弧段会以绿色小段高亮并单独统计最短可用弧段。
