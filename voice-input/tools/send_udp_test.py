"""模拟板子的无线回传包，用于在本机测试电脑端是否正常上屏。"""

from __future__ import annotations

import json
import socket
import sys


def main() -> None:
    text = sys.argv[1] if len(sys.argv) > 1 else "这是一条来自板子的无线识别结果。"
    host = sys.argv[2] if len(sys.argv) > 2 else "127.0.0.1"
    port = int(sys.argv[3]) if len(sys.argv) > 3 else 8899
    payload = json.dumps(
        {"app": "xl-dictate", "type": "iat", "seq": 1, "text": text}, ensure_ascii=False
    ).encode("utf-8")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sent = sock.sendto(payload, (host, port))
    print(f"sent {sent} bytes to {host}:{port} -> {text}")


if __name__ == "__main__":
    main()
