# 模型下载

模型文件较大（约 230 MB），不放进 Git 仓库。运行下载脚本即可：

```powershell
.\tools\download_models.ps1
```

脚本会下载并整理成：

```
models/
├─ sensevoice/
│  ├─ model.int8.onnx     ~228 MB   SenseVoiceSmall int8
│  └─ tokens.txt
└─ silero_vad.onnx        ~0.6 MB   Silero VAD
```

## 手动步骤（macOS / Linux）

```bash
mkdir -p models && cd models
curl -LO https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17.tar.bz2
tar -xjf sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17.tar.bz2
mkdir -p sensevoice
cp sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17/model.int8.onnx sensevoice/
cp sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17/tokens.txt sensevoice/
rm -rf sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17 sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17.tar.bz2

curl -LO https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx
```

## 许可证

- SenseVoice：[FunAudioLLM/SenseVoice](https://github.com/FunAudioLLM/SenseVoice)（模型遵循其模型许可）
- Silero VAD：[snakers4/silero-vad](https://github.com/snakers4/silero-vad)（MIT）
- 推理框架：[k2-fsa/sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx)（Apache-2.0）
