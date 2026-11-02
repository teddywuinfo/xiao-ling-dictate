# 下载 SenseVoice + Silero VAD 模型到 voice-input/models
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$models = Join-Path $root "models"
$svDir = Join-Path $models "sensevoice"
$tarName = "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17"

New-Item -ItemType Directory -Force $models, $svDir | Out-Null

if (-not (Test-Path (Join-Path $svDir "model.int8.onnx"))) {
    $tar = Join-Path $models "$tarName.tar.bz2"
    if (-not (Test-Path $tar)) {
        Write-Host "下载 SenseVoice（约 1 GB，含 fp32/int8 多份，取 int8）..."
        curl.exe -L --retry 3 -o $tar "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/$tarName.tar.bz2"
    }
    Write-Host "解包..."
    tar -xjf $tar -C $models
    Copy-Item (Join-Path $models "$tarName\model.int8.onnx") (Join-Path $svDir "model.int8.onnx") -Force
    Copy-Item (Join-Path $models "$tarName\tokens.txt") (Join-Path $svDir "tokens.txt") -Force
    Remove-Item $tar -Force
    Remove-Item (Join-Path $models $tarName) -Recurse -Force
}

$vad = Join-Path $models "silero_vad.onnx"
if (-not (Test-Path $vad)) {
    Write-Host "下载 Silero VAD..."
    curl.exe -L --retry 3 -o $vad "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx"
}

Get-ChildItem $models -Recurse -File | Select-Object @{n = "文件"; e = { $_.FullName.Replace($models, "") } },
    @{n = "大小(MB)"; e = { [math]::Round($_.Length / 1MB, 1) } } | Format-Table -AutoSize
