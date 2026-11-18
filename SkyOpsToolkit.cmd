@echo off
setlocal DisableDelayedExpansion
cd /d "%~dp0"
chcp 936 >nul
set "SKYOPS_PYTHON="
if defined CONDA_PREFIX (
    for %%D in ("%CONDA_PREFIX%") do if /i "%%~nxD"=="SkyOps" call :find_python "%%~fD"
)
if not defined SKYOPS_PYTHON (
    for /f "delims=" %%P in ('where.exe python.exe 2^>nul') do call :find_python "%%~dpPenvs\SkyOps"
)
if not defined SKYOPS_PYTHON call :find_python "D:\Anaconda3\envs\SkyOps"
if not defined SKYOPS_PYTHON call :find_python "D:\Software\Anaconda3\envs\SkyOps"

:MENU
title SkyOps 工具箱
cls
echo ==================================================
echo                  SkyOps 工具箱
echo ==================================================
echo  打开工具
echo    [1] 月度项目分配
echo    [2] 卫星试验记录
echo    [3] 全球通信仿真
echo.
echo  打包发布
echo    [4] 打包仿真桌面版
echo    [5] 打包月度项目分配
echo.
echo    [0] 退出
echo ==================================================
:READ_OPTION
set "SKYOPS_SELECTION="
set /p "SKYOPS_SELECTION=请输入编号 [1/2/3/4/5/0] 后按回车："
if not defined SKYOPS_SELECTION goto READ_OPTION
call :parse_selection
if errorlevel 6 goto INVALID_OPTION
if errorlevel 5 goto BUILD_MPAM
if errorlevel 4 goto BUILD_SIM
if errorlevel 3 goto SIM
if errorlevel 2 goto SAT
if errorlevel 1 goto MPAM
exit /b 0

:INVALID_OPTION
echo 编号无效，请重新输入。
goto READ_OPTION

:MPAM
call "%~dp0MPAM\MPAM.cmd"
goto MENU

:SAT
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0SatLog\scripts\start_skyops.ps1"
goto MENU

:SIM
call :require_python
if errorlevel 1 goto MENU
setlocal
set "PYTHONPATH=%~dp0STKSimulation\GlobalCommunicationSimulation\src"
"%SKYOPS_PYTHON%" -s -B -X utf8 -m stk_simulation
if errorlevel 1 pause
endlocal
goto MENU

:BUILD_SIM
call :require_python
if errorlevel 1 goto MENU
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0STKSimulation\GlobalCommunicationSimulation\packaging\build.ps1"
pause
goto MENU

:BUILD_MPAM
call :require_python
if errorlevel 1 goto MENU
"%SKYOPS_PYTHON%" -s -B -X utf8 "%~dp0MPAM\packaging\build.py"
if errorlevel 1 echo 打包失败，请查看上方输出。
pause
goto MENU

:require_python
if defined SKYOPS_PYTHON exit /b 0
echo 未找到 SkyOps 环境。请激活 SkyOps 后重新打开本菜单。
pause
exit /b 1

:find_python
if defined SKYOPS_PYTHON exit /b
if exist "%~1\python.exe" set "SKYOPS_PYTHON=%~1\python.exe"
exit /b

:parse_selection
setlocal EnableDelayedExpansion
for %%N in (0 1 2 3 4 5) do (
    if "!SKYOPS_SELECTION!"=="%%N" (
        endlocal
        exit /b %%N
    )
)
endlocal
exit /b 6
