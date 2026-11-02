"""把文字送到当前光标处：逐字键入（SendInput/Unicode）或剪贴板粘贴。"""

from __future__ import annotations

import ctypes
import threading
import time
from ctypes import wintypes

import pyperclip

user32 = ctypes.WinDLL("user32", use_last_error=True)

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
VK_CONTROL = 0x11
VK_V = 0x56
ULONG_PTR = ctypes.c_size_t  # 指针宽度：x64 下 8 字节，结构体必须是 40 字节


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


def _send(inputs: list[INPUT]) -> None:
    if not inputs:
        return
    array = (INPUT * len(inputs))(*inputs)
    user32.SendInput(len(inputs), array, ctypes.sizeof(INPUT))


def _key_input(scan: int, flags: int, vk: int = 0) -> INPUT:
    item = INPUT()
    item.type = INPUT_KEYBOARD
    item.ki = KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=0)
    return item


def type_text(text: str, char_delay_ms: int = 0) -> None:
    """按 Unicode 逐字键入，不依赖输入法和剪贴板。"""
    if not text:
        return
    units: list[int] = []
    encoded = text.encode("utf-16-le")
    for i in range(0, len(encoded), 2):
        units.append(int.from_bytes(encoded[i : i + 2], "little"))

    if char_delay_ms <= 0:
        batch: list[INPUT] = []
        for unit in units:
            batch.append(_key_input(unit, KEYEVENTF_UNICODE))
            batch.append(_key_input(unit, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP))
        _send(batch)
        return

    for unit in units:
        _send(
            [
                _key_input(unit, KEYEVENTF_UNICODE),
                _key_input(unit, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP),
            ]
        )
        time.sleep(char_delay_ms / 1000.0)


def paste_text(text: str, restore_delay: float = 0.35) -> None:
    """写入剪贴板并 Ctrl+V，随后恢复原剪贴板内容。"""
    if not text:
        return
    try:
        previous = pyperclip.paste()
    except Exception:  # noqa: BLE001
        previous = None
    pyperclip.copy(text)
    time.sleep(0.02)
    _send(
        [
            _key_input(0x1D, 0, VK_CONTROL),  # Ctrl down
            _key_input(0x2F, 0, VK_V),        # V down
            _key_input(0x2F, KEYEVENTF_KEYUP, VK_V),
            _key_input(0x1D, KEYEVENTF_KEYUP, VK_CONTROL),
        ]
    )
    if previous is not None:
        def _restore() -> None:
            time.sleep(restore_delay)
            try:
                pyperclip.copy(previous)
            except Exception:  # noqa: BLE001
                pass

        threading.Thread(target=_restore, daemon=True).start()


def insert_text(text: str, mode: str = "type", char_delay_ms: int = 0) -> None:
    """按配置的方式把文本上屏。"""
    if not text:
        return
    if mode == "paste":
        paste_text(text)
    else:
        type_text(text, char_delay_ms=char_delay_ms)
