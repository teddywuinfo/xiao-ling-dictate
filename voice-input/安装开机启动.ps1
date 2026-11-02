# 把小聆听写加入开机启动（可选，随时可撤销）
param([switch]$Remove)

$startup = [Environment]::GetFolderPath("Startup")
$link = Join-Path $startup "小聆听写.lnk"
$target = Join-Path $PSScriptRoot "启动小聆听写.vbs"

if ($Remove) {
    if (Test-Path $link) {
        Remove-Item $link -Force
        Write-Host "已取消开机启动。"
    } else {
        Write-Host "本来就没有设置开机启动。"
    }
    exit 0
}

if (-not (Test-Path $target)) {
    Write-Host "找不到 $target"
    exit 1
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($link)
$shortcut.TargetPath = $target
$shortcut.WorkingDirectory = $PSScriptRoot
$shortcut.Description = "小聆听写：对着板子说话，文字落到光标处"
$shortcut.Save()
Write-Host "已加入开机启动：$link"
