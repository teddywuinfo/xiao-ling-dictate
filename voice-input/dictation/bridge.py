"""本机 HTTP 服务：给设备上的 Lua 小应用查询状态、触发开关。"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable


class _Handler(BaseHTTPRequestHandler):
    server_version = "LingDictateBridge/1.0"

    # 由 Bridge.start 注入
    get_state: Callable[[], dict]
    toggle: Callable[[], dict]
    set_armed: Callable[[bool], dict]

    def _reply(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path in ("/state", "/", "/ping"):
            self.server.bridge.note_hit(self.client_address[0])  # type: ignore[attr-defined]
            self._reply(self.get_state())
        elif path == "/toggle":
            self.server.bridge.note_hit(self.client_address[0])  # type: ignore[attr-defined]
            self._reply(self.toggle())
        elif path == "/arm":
            self.server.bridge.note_hit(self.client_address[0])  # type: ignore[attr-defined]
            self._reply(self.set_armed(True))
        elif path == "/disarm":
            self.server.bridge.note_hit(self.client_address[0])  # type: ignore[attr-defined]
            self._reply(self.set_armed(False))
        else:
            self._reply({"error": "not found"}, status=404)

    def do_POST(self) -> None:  # noqa: N802
        # 读掉请求体，避免连接被复位
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        path = self.path.split("?", 1)[0]
        if path == "/toggle":
            self.server.bridge.note_hit(self.client_address[0])  # type: ignore[attr-defined]
            self._reply(self.toggle())
        elif path == "/arm":
            self.server.bridge.note_hit(self.client_address[0])  # type: ignore[attr-defined]
            self._reply(self.set_armed(True))
        elif path == "/disarm":
            self.server.bridge.note_hit(self.client_address[0])  # type: ignore[attr-defined]
            self._reply(self.set_armed(False))
        elif path == "/state":
            self.server.bridge.note_hit(self.client_address[0])  # type: ignore[attr-defined]
            self._reply(self.get_state())
        else:
            self._reply({"error": "not found"}, status=404)

    def log_message(self, *args) -> None:  # noqa: ANN002
        pass


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    bridge: "Bridge"


class Bridge:
    def __init__(
        self,
        port: int,
        get_state: Callable[[], dict],
        toggle: Callable[[], dict],
        set_armed: Callable[[bool], dict] | None = None,
    ) -> None:
        self.port = int(port)
        self._get_state = get_state
        self._toggle = toggle
        self._set_armed = set_armed or (lambda _armed: get_state())
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.last_error = ""
        self.hits = 0
        self.last_hit_at = 0.0
        self.last_client = ""

    def note_hit(self, client: str) -> None:
        self.hits += 1
        self.last_hit_at = time.time()
        self.last_client = client

    @property
    def running(self) -> bool:
        return self._server is not None

    def start(self) -> None:
        if self._server is not None:
            return
        handler = type(
            "BoundHandler",
            (_Handler,),
            {
                "get_state": staticmethod(self._get_state),
                "toggle": staticmethod(self._toggle),
                "set_armed": staticmethod(self._set_armed),
            },
        )
        try:
            server = _Server(("0.0.0.0", self.port), handler)
        except OSError as exc:
            self.last_error = f"端口 {self.port} 被占用：{exc}"
            raise RuntimeError(self.last_error) from exc
        server.bridge = self
        self._server = server
        self._thread = threading.Thread(target=server.serve_forever, daemon=True, name="bridge")
        self._thread.start()

    def stop(self) -> None:
        server, self._server = self._server, None
        if server is not None:
            server.shutdown()
            server.server_close()
