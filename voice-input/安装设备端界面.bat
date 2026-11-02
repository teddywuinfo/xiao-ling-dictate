@echo off
chcp 65001 >nul
cd /d "%~dp0"
setlocal enabledelayedexpansion
set "LUA=%~dp0device\ling-dictate.lua"

set "DEFAULT_IP="
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do (
    for /f "tokens=* delims= " %%b in ("%%a") do (
        if not defined DEFAULT_IP set "DEFAULT_IP=%%b"
    )
)

echo.
echo PC LAN IP suggestion: %DEFAULT_IP%
set /p "IP=Enter PC IP written into device script (Enter = use above): "
if "%IP%"=="" set "IP=%DEFAULT_IP%"

if "%IP%"=="" (
    echo No IP. Edit PC_HOST in device\ling-dictate.lua manually.
    pause
    exit /b 1
)

powershell -NoProfile -Command "$p='%LUA%'; $t=Get-Content -Raw -Encoding UTF8 $p; $t=$t -replace 'local PC_HOST = \"[^\"]*\"','local PC_HOST = \"%IP%\"'; [IO.File]::WriteAllText($p,$t,(New-Object Text.UTF8Encoding($false)))"
echo PC_HOST set to %IP%

where adb.exe >nul 2>nul
if errorlevel 1 (
    echo adb not found. Install Android Platform Tools and add to PATH.
    pause
    exit /b 1
)

adb devices
adb push "%LUA%" /miniapp/ling-dictate.lua
if errorlevel 1 (
    echo.
    echo Push failed: check USB connection and adb devices.
)
pause