@echo off
setlocal
cd /d "%~dp0"
set "PY=D:\Software\Anaconda3\envs\stk\python.exe"
if not exist "%PY%" set "PY=python"

:MENU
cls
echo ==================================================
echo    SkyOps 航天综合仿真平台 —— 一键工具
echo ==================================================
echo    [1] 直接运行（源码，免打包）
echo    [2] 打包编译（生成 SkyOpsSim.exe，不运行）
echo    [0] 退出
echo ==================================================
set /p choice=请输入选项 (1/2/0): 

if "%choice%"=="1" goto RUN
if "%choice%"=="2" goto BUILD
if "%choice%"=="0" exit /b 0
echo 无效选项，请重新输入。
timeout /t 1 >nul
goto MENU

:RUN
echo 正在从源码启动 SkyOps ...
echo 使用 Python: %PY%
set "PYTHONPATH=%~dp0src"
"%PY%" -m stk_simulation
if errorlevel 1 (
    echo.
    echo 启动失败。请确认 stk 环境已安装依赖：
    echo   "%PY%" -m pip install numpy scipy matplotlib PySide6 basemap skyfield sgp4
    pause
)
goto MENU

:BUILD
echo 正在调用打包脚本 build.ps1 ...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0packaging\build.ps1"
echo 打包完成，产物在 dist\SkyOpsSim.exe
timeout /t 1 >nul
goto MENU
