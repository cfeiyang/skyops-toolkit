@echo off
cd /d "%~dp0"
set "PY=D:\Software\Anaconda3\envs\skyops\pythonw.exe"
if not exist "%PY%" set "PY=pythonw"
start "" "%PY%" main.py
exit