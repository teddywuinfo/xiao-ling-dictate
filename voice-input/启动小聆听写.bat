@echo off
rem xiaoling dictate launcher (no console)
cd /d "%~dp0"

where pythonw.exe >nul 2>nul
if errorlevel 1 (
    echo pythonw.exe not found. Please install Python 3.10+ and add it to PATH.
    pause
    exit /b 1
)

start "" pythonw.exe "%~dp0app.py"
exit /b 0