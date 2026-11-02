# 第三方组件与许可证

本仓库不包含下列项目的源码或模型文件，只通过依赖 / 下载脚本使用它们。

| 组件 | 用途 | 许可证 / 来源 |
| --- | --- | --- |
| sherpa-onnx | 语音识别与 VAD 推理 | Apache-2.0 · <https://github.com/k2-fsa/sherpa-onnx> |
| SenseVoiceSmall | 离线中英日韩粤识别模型 | 模型许可见 <https://github.com/FunAudioLLM/SenseVoice> |
| Silero VAD | 语音活动检测 | MIT · <https://github.com/snakers4/silero-vad> |
| PySide6 / Qt | 桌面界面 | LGPL-3.0（Qt）· <https://www.qt.io/> |
| pynput | 全局热键 | LGPL-3.0 · <https://github.com/moses-palmer/pynput> |
| sounddevice | 音频采集 | MIT · <https://github.com/spatialaudio/python-sounddevice> |
| ARCS-Mini 固件 | 设备固件（本项目仅以补丁形式修改） | 见上游 <https://cloud.listenai.com/CSKG836746/arcs-sdk/public/arcs_mini> |
| LingClaw Lua SDK | 小应用 API 参考 | 见 <https://github.com/LISTENAI/LingClaw-SDK> |

固件补丁以 diff 形式提供，不重新分发上游源码；使用前请先取得上游代码并遵守其许可证。
