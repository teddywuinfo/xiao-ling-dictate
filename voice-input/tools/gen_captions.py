"""生成字幕 JSON（Caption 结构），按旁白音频时长与标点分配时间。"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

RUN = Path(
    r"C:\Users\Administrator\.dsh\data\dsh-remotion\projects"
    r"\f870857c-4b06-48f5-b883-3494191c94b5\runs\103e7193-4833-4f16-a34e-8994b0b1a715"
)
ASSETS = RUN / "public" / "assets"

# (场景开始秒, 音频文件, 旁白原文)
NARRATION = [
    (0.0, "voice-1.wav", "小聆听写：对着板子说话，文字直接落到电脑光标处。"),
    (30.5, "voice-3.wav", "插着线，板子当麦克风，电脑本地离线识别；拔了线，板子云端识别，通过 WiFi 把文字传回来。"),
    (39.9, "voice-4.wav", "声音先自动断句，再由 SenseVoice 在本机识别，最后逐字键入光标处。"),
    (47.1, "voice-5.wav", "五秒语音，零点二秒出字；全程离线，语音不出局域网。"),
    (53.5, "voice-6.wav", "小聆听写，现在就试试。"),
]

VOICE_OFFSET = 0.35

# 真实录屏段（无旁白）的手写字幕
REAL_CAPTIONS = [
    (6.6, 10.4, "左边是摄像头对着板子"),
    (10.4, 14.6, "板子屏幕显示：小聆听写 · 听写中"),
    (14.6, 18.6, "右边电脑输入框同步收到文字"),
    (19.2, 21.2, "放大看板子屏幕：最近一句就在下面"),
    (22.0, 29.8, "整个过程不用碰键盘，也不用切窗口"),
]


def duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(json.loads(out.stdout)["format"]["duration"])


def split_phrases(text: str) -> list[str]:
    parts = [p for p in re.split(r"[，。；、]", text) if p.strip()]
    return [p.strip() for p in parts]


def main() -> None:
    captions = []
    for start, wav, text in NARRATION:
        d = duration(ASSETS / wav)
        phrases = split_phrases(text)
        total_chars = sum(len(p) for p in phrases) or 1
        t = start + VOICE_OFFSET
        for p in phrases:
            share = d * len(p) / total_chars
            captions.append(
                {
                    "text": p,
                    "startMs": int(round(t * 1000)),
                    "endMs": int(round((t + share) * 1000)),
                    "timestampMs": None,
                    "confidence": None,
                }
            )
            t += share

    for s, e, text in REAL_CAPTIONS:
        captions.append(
            {
                "text": text,
                "startMs": int(round(s * 1000)),
                "endMs": int(round(e * 1000)),
                "timestampMs": None,
                "confidence": None,
            }
        )

    captions.sort(key=lambda c: c["startMs"])
    (RUN / "captions.json").write_text(json.dumps(captions, ensure_ascii=False, indent=2), "utf-8")
    print(f"wrote {len(captions)} captions")


if __name__ == "__main__":
    main()
