"""列出系统输入设备，标出程序会选中哪一个。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sounddevice as sd

from dictation.audio import list_input_devices


def main() -> None:
    apis = [h["name"] for h in sd.query_hostapis()]
    print("系统全部输入设备：")
    for index, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] <= 0:
            continue
        api = apis[dev["hostapi"]]
        print(f"  [{index:2d}] {dev['name']:<45} api={api:<18} ch={dev['max_input_channels']}")

    print("\n程序按关键字 'CherryUSB' 找到的候选（按优先级）：")
    for dev in list_input_devices("CherryUSB"):
        print(f"  [{dev['index']:2d}] {dev['name']} [{dev['hostapi']}] ch={dev['channels']}")


if __name__ == "__main__":
    main()
