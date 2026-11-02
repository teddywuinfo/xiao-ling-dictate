@echo off
chcp 65001 >nul
cd /d "%~dp0"

where adb.exe >nul 2>nul
if errorlevel 1 (
    echo 找不到 adb，请安装 Android Platform Tools 并加入 PATH。
    pause
    exit /b 1
)

adb devices
adb push "%~dp0device\ling-dictate.lua" /miniapp/ling-dictate.lua
if errorlevel 1 (
    echo.
    echo 推送失败：确认板子已用 USB 连上电脑。
    pause
    exit /b 1
)

echo.
echo 已打开板子上的听写界面：
echo   按一下功能键 = 开始 / 停止听写
echo   长按 3 秒   = 退出界面
pause