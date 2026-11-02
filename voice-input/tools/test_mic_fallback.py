"""验证：找不到板子时是否会偷偷改用别的麦克风。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dictation.audio import MicCapture


def try_open(label: str, **kwargs) -> None:
    mic = MicCapture(**kwargs)
    try:
        name = mic.start()
        print(f"{label}: 打开了 {name}")
    except RuntimeError as exc:
        print(f"{label}: 失败 -> {exc}")
    finally:
        mic.stop()


if __name__ == "__main__":
    try_open("① 板子在，关键字 CherryUSB", keyword="CherryUSB", fallback=False)
    try_open("② 板子不在，默认不回退", keyword="没有这个设备XYZ", fallback=False)
    try_open("③ 板子不在，允许回退", keyword="没有这个设备XYZ", fallback=True)
