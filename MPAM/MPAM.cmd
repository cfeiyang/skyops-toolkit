@echo off
cd /d "%~dp0"
where pythonw >nul 2>nul
if not errorlevel 1 (start "" pythonw main.py) else (start "" python main.py)
exit
