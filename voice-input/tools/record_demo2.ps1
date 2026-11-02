# 录制真实听写演示：演示输入框 + 语音上屏
$ErrorActionPreference = "Continue"
Add-Type -AssemblyName System.Speech
Add-Type -AssemblyName System.Windows.Forms
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class F {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    [DllImport("user32.dll")] public static extern bool AttachThreadInput(uint a, uint b, bool attach);
    [DllImport("kernel32.dll")] public static extern uint GetCurrentThreadId();
    [DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr h);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
}
"@

$sink = "D:\dev\小聆AI\voice-input\tools\demo_sink.txt"
$raw = "D:\dev\小聆AI\shots\demo-raw.mp4"

$proc = Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -like '*输入框*' } | Select-Object -First 1
if (-not $proc) { Write-Host "FAIL: 演示窗口不在"; exit 1 }
$h = $proc.MainWindowHandle

function Focus-Editor {
    $fg = [F]::GetForegroundWindow()
    $fgPid = 0
    $fgThread = [F]::GetWindowThreadProcessId($fg, [ref]$fgPid)
    $myThread = [F]::GetCurrentThreadId()
    [F]::ShowWindow($h, 9) | Out-Null
    [F]::AttachThreadInput($myThread, $fgThread, $true) | Out-Null
    [F]::BringWindowToTop($h) | Out-Null
    [F]::SetForegroundWindow($h) | Out-Null
    [F]::AttachThreadInput($myThread, $fgThread, $false) | Out-Null
}

Focus-Editor
Start-Sleep -Milliseconds 900

# 清空并自检焦点
[System.Windows.Forms.SendKeys]::SendWait("^a")
Start-Sleep -Milliseconds 200
[System.Windows.Forms.SendKeys]::SendWait("{DEL}")
Start-Sleep -Milliseconds 300
[System.Windows.Forms.SendKeys]::SendWait("check123")
Start-Sleep -Milliseconds 1200
$content = Get-Content $sink -Raw -ErrorAction SilentlyContinue
if ($content -notmatch 'check123') {
    Write-Host "FAIL: 没有焦点，放弃录制"
    exit 2
}
[System.Windows.Forms.SendKeys]::SendWait("^a")
Start-Sleep -Milliseconds 200
[System.Windows.Forms.SendKeys]::SendWait("{DEL}")
Start-Sleep -Milliseconds 500
Write-Host "焦点就绪，开始录制"

if (Test-Path $raw) { Remove-Item $raw -Force }
$ff = Start-Process -FilePath "ffmpeg" -ArgumentList @(
    "-y", "-f", "gdigrab", "-framerate", "30", "-i", "desktop",
    "-t", "22", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20", "-pix_fmt", "yuv420p", $raw
) -PassThru -WindowStyle Hidden

Start-Sleep 3
Focus-Editor
Start-Sleep -Milliseconds 600

$sp = New-Object System.Speech.Synthesis.SpeechSynthesizer
$sp.SelectVoice("Microsoft Huihui Desktop")
$sp.Volume = 100
$sp.Rate = 0
$sp.Speak("明天下午三点开项目评审会，记得带上设计稿。")
Start-Sleep 2
$sp.Speak("下周一之前把测试报告发给我。")

$ff.WaitForExit()
Write-Host "录制完成 exit=$($ff.ExitCode)"
$final = Get-Content $sink -Raw -ErrorAction SilentlyContinue
[IO.File]::WriteAllText("D:\dev\小聆AI\shots\demo-result.txt", "上屏内容:$final", (New-Object Text.UTF8Encoding($false)))
Write-Host ("文件 {0} ({1:N2} MB)" -f $raw, ((Get-Item $raw).Length / 1MB))
