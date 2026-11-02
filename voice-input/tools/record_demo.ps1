# 录制真实听写演示（记事本 + 光标上屏）
$ErrorActionPreference = "Continue"
Add-Type -AssemblyName System.Speech
Add-Type -AssemblyName System.Windows.Forms
Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public class WinApi {
    [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint flags);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern int GetWindowTextW(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
}
"@

function Get-ForegroundTitle {
    $h = [WinApi]::GetForegroundWindow()
    $sb = New-Object System.Text.StringBuilder 256
    [WinApi]::GetWindowTextW($h, $sb, 256) | Out-Null
    return $sb.ToString()
}

# 1. 找到已有的记事本窗口
$proc = Get-Process -Name Notepad -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
if (-not $proc) {
    Start-Process notepad | Out-Null
    for ($i = 0; $i -lt 20; $i++) {
        Start-Sleep -Milliseconds 500
        $proc = Get-Process -Name Notepad -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
        if ($proc) { break }
    }
}
if (-not $proc) { Write-Host "FAIL: 没有记事本窗口"; exit 1 }

$h = $proc.MainWindowHandle
[WinApi]::ShowWindow($h, 9) | Out-Null
[WinApi]::SetWindowPos($h, [IntPtr]::Zero, 360, 150, 1000, 620, 0x0040) | Out-Null
[WinApi]::SetForegroundWindow($h) | Out-Null
Start-Sleep -Milliseconds 800

# 清空内容
[System.Windows.Forms.SendKeys]::SendWait("^a")
Start-Sleep -Milliseconds 200
[System.Windows.Forms.SendKeys]::SendWait("{DEL}")
Start-Sleep -Milliseconds 400

$title = Get-ForegroundTitle
Write-Host "前台窗口: $title"
if ($title -notmatch 'Notepad|记事本') {
    Write-Host "FAIL: 记事本没有拿到焦点，放弃录制"
    exit 2
}

# 2. 录屏
$raw = "D:\dev\小聆AI\shots\demo-raw.mp4"
if (Test-Path $raw) { Remove-Item $raw -Force }
$ff = Start-Process -FilePath "ffmpeg" -ArgumentList @(
    "-y", "-f", "gdigrab", "-framerate", "30", "-i", "desktop",
    "-t", "22", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20", "-pix_fmt", "yuv420p", $raw
) -PassThru -WindowStyle Hidden

Start-Sleep 3
Write-Host "前台窗口(录制中): $(Get-ForegroundTitle)"

# 3. 说话 → 板子麦克风听到 → 文字打到记事本
$sp = New-Object System.Speech.Synthesis.SpeechSynthesizer
$sp.SelectVoice("Microsoft Huihui Desktop")
$sp.Volume = 100
$sp.Rate = 0
$sp.Speak("明天下午三点开项目评审会，记得带上设计稿。")
Start-Sleep 2
$sp.Speak("下周一之前把测试报告发给我。")

$ff.WaitForExit()
Write-Host "录制完成 exit=$($ff.ExitCode)"
if (Test-Path $raw) { Write-Host ("文件 {0} ({1:N2} MB)" -f $raw, ((Get-Item $raw).Length / 1MB)) }
