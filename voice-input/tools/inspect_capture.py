"""检查录下来的音频：能量、VAD、识别结果。"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dictation.asr import SenseVoice, VadSegmenter  # noqa: E402
from dictation.config import Config  # noqa: E402

cfg = Config.load()
wav = Path(__file__).parent / "loop_capture.wav"
data, sr = sf.read(str(wav), dtype="float32")
if data.ndim > 1:
    data = data[:, 0]
print("file", wav.name, "dur", len(data) / sr, "peak", float(np.abs(data).max()))

w = int(sr * 0.25)
for i in range(0, len(data) - w + 1, w):
    seg = data[i : i + w]
    print(f"  t={i/sr:5.2f}s rms={np.sqrt(np.mean(seg**2)):.4f} peak={np.abs(seg).max():.3f}")

rec = SenseVoice(cfg.asr_model, cfg.asr_tokens, cfg.num_threads, cfg.language, cfg.use_itn)
print("whole-file ASR:", repr(rec.transcribe(data)))

for thr in (0.3, 0.5, 0.7):
    vad = VadSegmenter(cfg.vad_model, thr, cfg.min_silence_ms, 100, cfg.max_speech_s)
    n = 0
    for i in range(0, len(data) - 512 + 1, 512):
        for seg in vad.push(data[i : i + 512]):
            n += 1
            print(f"  thr={thr} seg {len(seg)/16000:.2f}s {rec.transcribe(seg)!r}")
    print(f"thr={thr} segments={n}")
