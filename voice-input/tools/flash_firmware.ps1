# 小聆听写 · 固件烧录（app 分区）
# 规避两个坑：
#   1. Windows PowerShell 5.1 把 adb 的 stderr 当成错误、脚本中途退出
#   2. 漏掉 `adb shell recovery exit` 导致分区没写完就断电（会变砖）
param(
    [string]$Firmware = "X:\arcs_mini\build-dictate3\arcs-mini.bin",
    [string]$Adb = "X:\arcs_mini\tools\adb\adb.exe",
    [string]$Remote = "/RAW/NAND/600000",
    [int]$TimeoutSec = 180
)

$ErrorActionPreference = "Continue"

function Invoke-Adb {
    param([string[]]$Arguments)
    $outFile = Join-Path $env:TEMP "adb-flash-out.txt"
    $errFile = Join-Path $env:TEMP "adb-flash-err.txt"
    $p = Start-Process -FilePath $Adb -ArgumentList $Arguments `
        -RedirectStandardOutput $outFile -RedirectStandardError $errFile `
        -PassThru -Wait -NoNewWindow
    $out = if (Test-Path $outFile) { (Get-Content $outFile -Raw -ErrorAction SilentlyContinue) } else { "" }
    $err = if (Test-Path $errFile) { (Get-Content $errFile -Raw -ErrorAction SilentlyContinue) } else { "" }
    return [pscustomobject]@{ Code = $p.ExitCode; Out = $out; Err = $err }
}

function Get-Devices {
    $r = Invoke-Adb @("devices", "-l")
    return $r.Out
}

if (-not (Test-Path $Firmware)) { Write-Host "固件不存在: $Firmware"; exit 1 }
if (-not (Test-Path $Adb)) { Write-Host "adb 不存在: $Adb"; exit 1 }

Write-Host "固件: $Firmware ($([math]::Round((Get-Item $Firmware).Length/1MB,2)) MB)"

$devices = Get-Devices
Write-Host "当前设备:`n$devices"

# 1. 普通模式 → 让设备进 recovery
if ($devices -match '6d7b101a5e3ecba5\s+device' -and $devices -notmatch 'BOOT-') {
    Write-Host "让设备进入 recovery..."
    Invoke-Adb @("reboot", "recovery") | Out-Null
}

# 2. 等 BOOT 设备上线
$deadline = (Get-Date).AddSeconds($TimeoutSec)
$serial = $null
while ((Get-Date) -lt $deadline) {
    $d = Get-Devices
    $m = [regex]::Match($d, 'BOOT-(\S+)\s+device')
    if ($m.Success) { $serial = "BOOT-" + $m.Groups[1].Value; break }
    $m2 = [regex]::Match($d, 'BOOT-(\S+)\s+offline')
    if ($m2.Success) {
        # 老 boot 需要握手才会从 offline 变成 device
        $id = $m2.Groups[1].Value
        Invoke-Adb @("-s", "BOOT-$id", "shell", $id) | Out-Null
    }
    Start-Sleep 2
}
if (-not $serial) { Write-Host "等待 recovery 超时（设备没进烧录模式）"; exit 2 }
Write-Host "recovery 设备: $serial"

# 3. 握手（保险起见再发一次）
$id = $serial.Substring(5)
Invoke-Adb @("-s", $serial, "shell", $id) | Out-Null
Start-Sleep 4

# 4. push
Write-Host "写入 app 分区（约 45 秒）..."
$r = Invoke-Adb @("-s", $serial, "push", $Firmware, $Remote)
Write-Host "push 退出码: $($r.Code)"
if ($r.Code -ne 0) {
    Write-Host ($r.Err + $r.Out)
    Write-Host "push 失败，设备仍在 recovery，可重试；不要直接断电！"
    exit 3
}

# 5. 提交 + 重启（顺序不能改）
Write-Host "recovery exit ..."
$r1 = Invoke-Adb @("-s", $serial, "shell", "recovery", "exit")
Write-Host "  exit 码: $($r1.Code)"
Start-Sleep 2
Write-Host "reboot hard ..."
$r2 = Invoke-Adb @("-s", $serial, "shell", "reboot", "hard")
Write-Host "  reboot 码: $($r2.Code)"

Write-Host ""
Write-Host "烧录完成。设备会重启（可能需要长按开机键）。"
Write-Host "验证：adb devices 出现 6d7b101a5e3ecba5 device 即成功。"
