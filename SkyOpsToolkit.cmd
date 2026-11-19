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


set "SKYOPS_ACCENT="
set "SKYOPS_MUTED="
set "SKYOPS_RESET="
if defined WT_SESSION (
    for /f "tokens=1,2 delims=+" %%E in ('echo prompt $E+SkyOpsAnsi+^| cmd.exe /d /q') do if "%%F"=="SkyOpsAnsi" (
        set "SKYOPS_ACCENT=%%E[96m"
        set "SKYOPS_MUTED=%%E[90m"
        set "SKYOPS_RESET=%%E[0m"
    )
)

:MENU
title SkyOps 工具箱
cls
color 0F
echo.
echo   %SKYOPS_ACCENT%SkyOps%SKYOPS_RESET%  工具箱
echo   %SKYOPS_MUTED%------------------------------------------------%SKYOPS_RESET%
echo.
echo   %SKYOPS_ACCENT%打开工具%SKYOPS_RESET%
echo     %SKYOPS_ACCENT%[1]%SKYOPS_RESET%  月度项目分配
echo     %SKYOPS_ACCENT%[2]%SKYOPS_RESET%  SkyOps 仿真桌面
echo          %SKYOPS_MUTED%全球覆盖 / 建链可见性 / STK 工作台%SKYOPS_RESET%
echo.
echo   %SKYOPS_ACCENT%打包发布%SKYOPS_RESET%
echo     %SKYOPS_ACCENT%[3]%SKYOPS_RESET%  SkyOps 仿真桌面版
echo     %SKYOPS_ACCENT%[4]%SKYOPS_RESET%  月度项目分配
echo.
echo   %SKYOPS_MUTED%------------------------------------------------%SKYOPS_RESET%
echo     %SKYOPS_ACCENT%[0]%SKYOPS_RESET%  退出
echo.
:READ_OPTION
set "SKYOPS_SELECTION="
set /p "SKYOPS_SELECTION=　输入编号并按回车： "
if not defined SKYOPS_SELECTION goto READ_OPTION
call :parse_selection
if errorlevel 5 goto INVALID_OPTION
if errorlevel 4 goto BUILD_MPAM
if errorlevel 3 goto BUILD_SIM
if errorlevel 2 goto SIM
if errorlevel 1 goto MPAM
exit /b 0

:INVALID_OPTION
echo   请选择 1、2、3、4 或 0。
goto READ_OPTION

:MPAM
call "%~dp0MPAM\MPAM.cmd"
goto MENU

:SIM
call :require_python
if errorlevel 1 goto MENU
setlocal
set "PYTHONPATH=%~dp0SkyOpsSimulation"
"%SKYOPS_PYTHON%" -s -B -X utf8 -m skyops_sim
if errorlevel 1 pause
endlocal
goto MENU

:BUILD_SIM
call :require_python
if errorlevel 1 goto MENU
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0SkyOpsSimulation\packaging\build.ps1"
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
for %%N in (0 1 2 3 4) do (
    if "!SKYOPS_SELECTION!"=="%%N" (
        endlocal
        exit /b %%N
    )
)
endlocal
exit /b 5
