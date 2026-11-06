@echo off
setlocal
cd /d "%~dp0"
set "PY=D:\Software\Anaconda3\envs\skyops\python.exe"
set "PYW=D:\Software\Anaconda3\envs\skyops\pythonw.exe"
if not exist "%PY%"  set "PY=python"
if not exist "%PYW%" set "PYW=pythonw"

:MENU
cls
echo ==================================================
echo    SkyOps 工具箱 —— 启动管理
echo ==================================================
echo    [1] MPAM 月度项目分配管理
echo    [2] SatLog Web 原版（浏览器 8501）
echo    [3] SkyOps 桌面仿真（全球覆盖 + 建链）
echo    [4] 打包 SkyOpsSim.exe
echo    [0] 退出
echo ==================================================
set /p choice=请输入选项 (1/2/3/4/0): 

if "%choice%"=="1" goto MPAM
if "%choice%"=="2" goto SAT
if "%choice%"=="3" goto SKY
if "%choice%"=="4" goto BUILD
if "%choice%"=="0" exit /b 0
echo 无效选项，请重新输入。
timeout /t 1 >nul
goto MENU

:MPAM
start "" "%PYW%" "MPAM\main.py"
echo MPAM 已启动（登录 root / 123456）。
timeout /t 1 >nul
goto MENU

:SAT
echo 正在启动 SatLog Web ...
powershell -NoProfile -ExecutionPolicy Bypass -File "SatLog\scripts\start_skyops.ps1"
goto MENU

:SKY
echo 正在启动 SkyOps 桌面仿真 ...
set "PYTHONPATH=%~dp0STKSimulation\GlobalCommunicationSimulation\src"
"%PY%" -m stk_simulation
if errorlevel 1 (
    echo.
    echo 启动失败。请确认 skyops 环境已安装依赖。
    pause
)
goto MENU

:BUILD
echo 正在打包 SkyOpsSim.exe ...
powershell -NoProfile -ExecutionPolicy Bypass -File "STKSimulation\GlobalCommunicationSimulation\packaging\build.ps1"
timeout /t 1 >nul
goto MENU