"""闭环联调：一边播放 TTS，一边用板子麦克风采集，然后对录到的音频跑 VAD + 识别。"""

from __future__ import annotations

import asyncio
import sys
import tempfile
import threading
import time
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dictation.asr import SenseVoice, VadSegmenter, is_noise  # noqa: E402
from dictation.audio import MicCapture  # noqa: E402
from dictation.config import Config  # noqa: E402

TEXT = "今天下午三点开会，记得带上项目进度报告。"


def synth(text: str) -> str:
    import edge_tts

    out = str(Path(tempfile.gettempdir()) / "ling_loop.mp3")
    asyncio.run(edge_tts.Communicate(text, "zh-CN-XiaoxiaoNeural").save(out))
    return out


def main() -> None:
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 12.0
    channel = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    cfg = Config.load()
    recognizer = SenseVoice(cfg.asr_model, cfg.asr_tokens, cfg.num_threads, cfg.language, cfg.use_itn)
    segmenter = VadSegmenter(
        cfg.vad_model, cfg.vad_threshold, cfg.min_silence_ms, cfg.min_speech_ms, cfg.max_speech_s
    )
    mic = MicCapture(
        keyword=cfg.mic_keyword,
        device_index=cfg.mic_device_index,
        channel=channel,
        gain=cfg.input_gain,
    )
    print("mic:", mic.start())

    path = synth(TEXT)
    audio, sr = sf.read(path, dtype="float32")
    if audio.ndim > 1:
        audio = audio[:, 0]
    print(f"tts {len(audio)/sr:.2f}s")

    def play() -> None:
        time.sleep(1.5)
        print("play")
        sd.play(audio * 1.0, samplerate=sr)
        sd.wait()

    threading.Thread(target=play, daemon=True).start()

    collected = []
    results: list[str] = []
    t0 = time.time()
    while time.time() - t0 < seconds:
        block = mic.read(timeout=0.2)
        if block is None:
            continue
        collected.append(block)
        for seg in segmenter.push(block):
            text = recognizer.transcribe_with_gain(seg, gain=cfg.segment_gain)
            flag = " (noise)" if is_noise(text, len(seg) / 16000) else ""
            results.append(f"seg {len(seg)/16000:.2f}s -> {text}{flag}")
            print(f"  seg {len(seg)/16000:.2f}s -> {text!r}{flag}")
    for seg in segmenter.flush():
        text = recognizer.transcribe_with_gain(seg, gain=cfg.segment_gain)
        results.append(f"flush {len(seg)/16000:.2f}s -> {text}")
        print(f"  flush {len(seg)/16000:.2f}s -> {text!r}")
    mic.stop()
    Path(__file__).with_name("loop_result.txt").write_text(
        "TTS: " + TEXT + "\n" + "\n".join(results) + "\n", "utf-8"
    )

    if collected:
        data = np.concatenate(collected)
        wav = Path(__file__).parent / "loop_capture.wav"
        sf.write(str(wav), data, 16000)
        print("saved", wav, "dur", len(data) / 16000, "peak", float(np.abs(data).max()))


if __name__ == "__main__":
    main()
