# STK 12 仿真工作台

适用于 Windows 上的 **Ansys STK 12 Desktop**。没有安装 STK 的电脑也能打开工作台、填写参数并保存 Connect 命令。真正的场景创建和 Access 计算由安装了 STK 12 的电脑执行。

## 使用

1. 将 **STK12Workbench.exe** 复制到装有 STK 12 的电脑，双击打开。控制命令发送到当前电脑的 STK，不需要在 STK 中开启网络端口。
2. 点击 **启动 / 连接 STK**。STK 已经运行时会连接到现有实例。切换场景后可再点击该按钮刷新场景和对象列表。
3. 初次使用可选 **载入示例**。核对右侧预览，在 STK 未打开场景时点击 **执行整套流程**。示例创建一个一天的地球场景、一颗低轨卫星和一个地面站，并按 10° 最小仰角计算可见时段。
4. 日常使用可选左侧步骤单独执行。更新已存在的卫星或地面站时，取消勾选对应的创建选项。多颗卫星或多个站可以分次加入。
5. **执行结果**会显示 STK 回传的信息。单条命令失败时会停止后续步骤，前面成功的步骤仍然生效。修正出错项后，可以只执行剩下的步骤。

离线生成的 UTF-8 文本可带到 STK 电脑，从 **命令终端 → 打开命令文件** 载入并执行。命令中的星历、场景和导出路径由运行 STK 的电脑读取。两台电脑文件位置不同时，先在命令终端修改路径。

## 命令和单位

| 操作 | Connect 命令 |
| --- | --- |
| 创建、打开和保存场景 | [New](https://help.agi.com/stk/12.10.0/SubSystems/connectCmds/Content/cmd_New.htm)、[SetAnalysisTimePeriod](https://help.agi.com/stk/12.10.0/SubSystems/connectCmds/Content/cmd_SetAnalysisTimePeriod.htm)、[SetEpoch](https://help.agi.com/stkdevkit/12.0.0/Subsystems/connectCmds/Content/cmd_SetEpoch.htm)、[Load](https://help.agi.com/stk/12.10.0/SubSystems/connectCmds/Content/cmd_Load.htm)、[Save](https://help.agi.com/stk/12.10.0/SubSystems/connectCmds/Content/cmd_Save.htm) |
| 经典根数、TLE、星历文件 | [SetState Classical](https://help.agi.com/stkdevkit/12.0.0/Subsystems/connectCmds/Content/cmd_SetStateClassical.htm)、[SetState TLE](https://help.agi.com/stkdevkit/12.0.0/Subsystems/connectCmds/Content/cmd_SetStateTLESatellites.htm)、[SetState FromFile](https://help.agi.com/stkdevkit/12.0.0/Subsystems/connectCmds/Content/cmd_SetStateFromFile.htm)、[ExportDataFile](https://help.agi.com/stkdevkit/12.0.0/Subsystems/connectCmds/Content/cmd_ExportDataFile.htm) |
| 地面站和角度条件 | [SetPosition](https://help.agi.com/stk/12.10.0/SubSystems/connectCmds/Content/cmd_SetPositionFacilityPlaceTargetAreaTarget.htm)、[SetConstraint](https://help.agi.com/stkdevkit/12.0.0/Subsystems/connectCmds/Content/cmd_SetConstraintFacilityPlaceTarget.htm) |
| 计算地面站与卫星的可见窗口 | [Access](https://help.agi.com/stkdevkit/12.0.0/Subsystems/connectCmds/Content/cmd_Access.htm) |

- 表单用 UTC 时间、度、秒和米。半长轴便于录入，显示为 km，生成命令时转成 m。涉及单位的命令前会设置 [Connect 的默认单位](https://help.agi.com/stkdevkit/12.0.0/Subsystems/connectCmds/Content/cmd_Units_SetConnect.htm)。
- 最小仰角以地面站当地水平面为基准。太阳、月球和参考卫星隔离角针对从地面站指向目标卫星的视线。按 Ansys 文档，同一站点的 ObjectExclusionAngle 阈值适用于该站全部参考对象。
- TLE 和外部星历应覆盖拟分析时段或适用于该时段。工作台用场景开始时间作为经典根数历元。判断实际可见性时，需要使用有效的轨道和地面站参数。
- 当前工作流为地球场景的几何可见计算。实际可用命令和计算能力取决于目标机的 STK 小版本与许可证。

## 官方实例和界面参考

- [Ansys：Introduction to Connect](https://help.agi.com/stk/12.10.0/Content/training/L1_Connect.htm) 展示了如何查命令、创建对象和查询结果。
- [Ansys：Drive STK with Connect Commands and Excel](https://help.agi.com/stk/12.10.0/Content/training/Adv_Connect.htm) 展示了批量构造地面目标及约束命令的过程。
- [Ansys：Integrating STK with Python](https://help.agi.com/stk/12.7.0/Content/training/StartPython.htm) 展示了连接 STK 后创建 LEO 卫星和地面设施的例子。
- [Ansys：STK 12 桌面 COM 连接方法](https://help.agi.com/stkdevkit/12.2.0/Content/python/pythonMigrationGuide.htm) 给出了以 STK12.Application 启动或连接桌面的示例。工作台使用这一 COM 接口，将命令交给 Personality2.ExecuteCommand。
- [Microsoft：Windows 应用导航](https://learn.microsoft.com/en-us/windows/apps/design/controls/navigationview) 提供了左侧导航的布局参考。这里的步骤切换保留各页参数，右侧始终能看到将要发送的命令。

## 从源码运行

使用已有的 SkyOps 环境，在本目录运行 python -B main.py。窗口依赖 PySide6，STK 连接使用 Windows 自带的 Windows PowerShell 5.1。源码运行和 EXE 均使用相同的 Connect 命令生成逻辑。


## 重新打包

使用 SkyOps 环境运行 python -B -m PyInstaller STK12Workbench.spec。打包配置使用 Windows 自带的 ICU 库，以匹配 PySide6 对系统接口的要求。打包后可运行 STK12Workbench.exe --check-startup，检查应用能否在没有 STK 的电脑上创建窗口并正常退出。