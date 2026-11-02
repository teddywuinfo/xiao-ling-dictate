"""用 MiMo TTS 重新生成视频旁白，输出到 Remotion 工程 public/assets，并打印时长。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

RUN = Path(
    r"C:\Users\Administrator\.dsh\data\dsh-remotion\projects"
    r"\f870857c-4b06-48f5-b883-3494191c94b5\runs\103e7193-4833-4f16-a34e-8994b0b1a715"
)
ASSETS = RUN / "public" / "assets"
CLI = Path.home() / ".agents" / "skills" / "mimo-audio" / "scripts" / "mimo_audio.py"

LINES = [
    ("voice-1", "小聆听写：对着板子说话，文字直接落到电脑光标处。"),
    ("voice-2", "不用切窗口，也不用按住说话。说一句小聆小聆，帮我打开听写，板子就会把光标处变成输入框。"),
    ("voice-3", "插着线，板子当麦克风，电脑本地离线识别；拔了线，板子云端识别，通过 WiFi 把文字传回来。"),
    ("voice-4", "声音先自动断句，再由 SenseVoice 在本机识别，最后逐字键入光标处。"),
    ("voice-5", "五秒语音，零点二秒出字；全程离线，语音不出局域网。"),
    ("voice-6", "小聆听写，现在就试试。"),
]


def duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(json.loads(out.stdout)["format"]["duration"])


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    result = {}
    for name, text in LINES:
        out = ASSETS / f"{name}.wav"
        cmd = [
            sys.executable,
            str(CLI),
            "tts",
            "--text",
            text,
            "--voice",
            "冰糖",
            "--style",
            "自然、清晰、像产品介绍片旁白，语速适中",
            "--out",
            str(out),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"{name} 失败: {r.stdout} {r.stderr}")
            return
        d = duration(out)
        result[name] = round(d, 2)
        print(f"{name}: {d:.2f}s")
    print("total", round(sum(result.values()), 2))
    (RUN / "voices-mimo.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), "utf-8")


if __name__ == "__main__":
    main()
