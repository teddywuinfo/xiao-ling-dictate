"""无线听写：接收板子广播过来的识别文本（UDP 8899）。"""

from __future__ import annotations

import json
import socket
import threading
import time
from typing import Callable


class NetTextReceiver:
    """监听设备发来的 JSON 包：{"app":"xl-dictate","type":"iat","text":"..."}"""

    def __init__(self, port: int, on_text: Callable[[str], None]) -> None:
        self.port = int(port)
        self._on_text = on_text
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._running = threading.Event()
        self.hits = 0
        self.dup_skips = 0
        self.last_text = ""
        self.last_client = ""
        self.last_at = 0.0
        self.last_error = ""

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("0.0.0.0", self.port))
        except OSError as exc:
            sock.close()
            self.last_error = f"无线端口 {self.port} 绑定失败：{exc}"
            raise RuntimeError(self.last_error) from exc
        sock.settimeout(0.5)
        self._sock = sock
        self._running.set()
        self._thread = threading.Thread(target=self._loop, name="net-text", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running.clear()
        sock, self._sock = self._sock, None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        self._thread = None

    def _loop(self) -> None:
        while self._running.is_set():
            sock = self._sock
            if sock is None:
                break
            try:
                data, addr = sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            self._handle(data, addr[0])

    def _handle(self, data: bytes, client: str) -> None:
        try:
            payload = json.loads(data.decode("utf-8", "replace"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return
        if not isinstance(payload, dict):
            return
        if payload.get("app") != "xl-dictate":
            return
        if payload.get("type") != "iat":
            return
        text = payload.get("text")
        if not isinstance(text, str):
            return
        text = text.strip()
        if not text:
            return
        self.hits += 1
        self.last_client = client
        self.last_at = time.time()
        if text == self.last_text:
            # 设备偶尔会重复上报同一句（多轮回调），这里去重
            self.dup_skips += 1
            return
        self.last_text = text
        self._on_text(text)
