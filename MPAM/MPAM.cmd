@echo off
setlocal
cd /d "%~dp0"
set "MPAM_PYTHON="
if defined CONDA_PREFIX (
    for %%D in ("%CONDA_PREFIX%") do if /i "%%~nxD"=="SkyOps" call :find "%%~fD"
)
if not defined MPAM_PYTHON (
    for /f "delims=" %%P in ('where.exe python.exe 2^>nul') do call :find "%%~dpPenvs\SkyOps"
)
if not defined MPAM_PYTHON call :find "D:\Anaconda3\envs\SkyOps"
if not defined MPAM_PYTHON call :find "D:\Software\Anaconda3\envs\SkyOps"
if not defined MPAM_PYTHON (
    echo SkyOps environment not found. Activate it with: conda activate SkyOps
    pause
    exit /b 1
)
start "" "%MPAM_PYTHON%" -s -B "%~dp0main.py" %*
exit /b %errorlevel%

:find
if defined MPAM_PYTHON exit /b
if exist "%~1\pythonw.exe" set "MPAM_PYTHON=%~1\pythonw.exe"
exit /b
