"""把设备端 Lua 小应用转成固件里的 C 字节数组（内置到固件，语音指令可直接拉起）。"""

from __future__ import annotations

import hashlib
from pathlib import Path

LUA = Path(__file__).resolve().parent.parent / "device" / "ling-dictate.lua"
OUT = Path(r"X:\arcs_mini\src\server\lschat_server\dictate_app_lua.h")


def main() -> None:
    text = LUA.read_text("utf-8")
    data = text.encode("utf-8")
    md5 = hashlib.md5(data).hexdigest()

    lines = [
        "/* 自动生成，请勿手改。",
        " * 来源: voice-input/device/ling-dictate.lua",
        " * 生成: voice-input/tools/gen_dictate_app_header.py",
        " */",
        "#pragma once",
        "",
        "static const unsigned char k_dictate_app_lua[] = {",
    ]
    for i in range(0, len(data), 16):
        chunk = data[i : i + 16]
        lines.append("    " + ",".join(f"0x{b:02x}" for b in chunk) + ",")
    lines += [
        "};",
        f"#define DICTATE_APP_LUA_SIZE {len(data)}",
        f'#define DICTATE_APP_MD5 "{md5}"',
        '#define DICTATE_APP_ID "listenai.local.dictate"',
        '#define DICTATE_APP_VERSION "1.0.0"',
        "",
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), "utf-8")
    print(f"wrote {OUT} ({len(data)} bytes, md5 {md5})")


if __name__ == "__main__":
    main()
