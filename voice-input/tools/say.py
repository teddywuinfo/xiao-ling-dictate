"""用 edge-tts 合成一句话并播放，方便无麦克风环境下测试。"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

import sounddevice as sd
import soundfile as sf


async def synth(text: str, out: str, voice: str) -> None:
    import edge_tts

    await edge_tts.Communicate(text, voice).save(out)


def main() -> None:
    text = sys.argv[1] if len(sys.argv) > 1 else "这是一段测试语音，用来验证听写效果。"
    voice = sys.argv[2] if len(sys.argv) > 2 else "zh-CN-XiaoxiaoNeural"
    volume = float(sys.argv[3]) if len(sys.argv) > 3 else 0.95
    out = str(Path(tempfile.gettempdir()) / "ling_say.mp3")
    asyncio.run(synth(text, out, voice))
    audio, sr = sf.read(out, dtype="float32")
    if audio.ndim > 1:
        audio = audio[:, 0]
    print(f"play {len(audio)/sr:.2f}s @ {sr}Hz vol={volume}")
    sd.play(audio * volume, samplerate=sr)
    sd.wait()


if __name__ == "__main__":
    main()
