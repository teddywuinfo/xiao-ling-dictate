"""无界面联调：采集 → VAD → 识别，并把结果显示出来。"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dictation.asr import SenseVoice, VadSegmenter  # noqa: E402
from dictation.audio import MicCapture  # noqa: E402
from dictation.config import Config  # noqa: E402


def main() -> None:
    cfg = Config.load()
    print("model:", cfg.asr_model)
    recognizer = SenseVoice(
        model=cfg.asr_model,
        tokens=cfg.asr_tokens,
        num_threads=cfg.num_threads,
        language=cfg.language,
        use_itn=cfg.use_itn,
    )
    print(f"ASR 加载 {recognizer.load_seconds:.2f}s")
    segmenter = VadSegmenter(
        cfg.vad_model,
        threshold=cfg.vad_threshold,
        min_silence_ms=cfg.min_silence_ms,
        min_speech_ms=cfg.min_speech_ms,
        max_speech_s=cfg.max_speech_s,
    )
    mic = MicCapture(keyword=cfg.mic_keyword, device_index=cfg.mic_device_index, channel=cfg.mic_channel)
    label = mic.start()
    print("mic:", label)

    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 12.0
    t0 = time.time()
    count = 0
    peak = 0.0
    while time.time() - t0 < seconds:
        block = mic.read(timeout=0.3)
        if block is None:
            continue
        peak = max(peak, float(abs(block).max()))
        for seg in segmenter.push(block):
            dur = len(seg) / 16000
            t = time.time()
            text = recognizer.transcribe_with_gain(seg, gain=cfg.segment_gain)
            count += 1
            print(f"[{count}] {dur:.2f}s -> {time.time()-t:.2f}s  {text!r}")
    for seg in segmenter.flush():
        text = recognizer.transcribe_with_gain(seg, gain=cfg.segment_gain)
        count += 1
        print(f"[flush] {len(seg)/16000:.2f}s  {text!r}")
    mic.stop()
    print(f"peak={peak:.3f} segments={count}")


if __name__ == "__main__":
    main()
