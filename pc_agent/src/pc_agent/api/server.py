"""API HTTP của PC Agent.

Dùng `http.server` chuẩn của Python (không thêm framework) để giữ phụ thuộc
tối thiểu — đây là service chạy 24/7 trên máy chủ, mỗi dependency là một
rủi ro bảo mật và cập nhật.

Ràng buộc bảo mật:
  - mặc định chỉ bind `127.0.0.1`;
  - các endpoint thay đổi trạng thái yêu cầu `Authorization: Bearer <token>`
    nếu `api_token` được cấu hình.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse

LOG = logging.getLogger("pc_agent.api")

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


class AgentServer:
    """Bọc `ThreadingHTTPServer` thành đối tượng có thể start/stop."""

    def __init__(
        self,
        config,
        state,
        store,
        host: Optional[str] = None,
        port: Optional[int] = None,
    ) -> None:
        self.config = config
        self.state = state
        self.store = store
        self.host = host if host is not None else config.api_host
        self.port = port if port is not None else config.api_port
        self._httpd: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------ #
    def start(self) -> None:
        handler = _make_handler(self)
        self._httpd = ThreadingHTTPServer((self.host, self.port), handler)
        self._httpd.daemon_threads = True
        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            kwargs={"poll_interval": 0.5},
            name="HTTPServer",
            daemon=True,
        )
        self._thread.start()
        LOG.info("API sẵn sàng tại http://%s:%d/", self.host, self.port)

    def stop(self) -> None:
        if self._httpd is not None:
            try:
                self._httpd.shutdown()
                self._httpd.server_close()
            except Exception:  # noqa: BLE001
                pass
            self._httpd = None
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        self._thread = None
        LOG.info("API đã dừng.")


# --------------------------------------------------------------------------- #
# Handler
# --------------------------------------------------------------------------- #
def _make_handler(agent: AgentServer):
    class AgentHandler(BaseHTTPRequestHandler):
        server_version = "PCAgent/1.0"

        # -- tiện ích ---------------------------------------------------- #
        def log_message(self, fmt, *args):  # noqa: A003
            LOG.debug("%s - %s", self.address_string(), fmt % args)

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, payload: Any) -> None:
            body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
            self._send(status, body, "application/json; charset=utf-8")

        def _authorized(self) -> bool:
            """Kiểm tra Bearer token nếu được cấu hình."""
            token = agent.config.api_token
            if not token:
                return True
            header = self.headers.get("Authorization", "")
            if not header.startswith("Bearer "):
                return False
            return header.split("Bearer ", 1)[1].strip() == token

        # -- routes ------------------------------------------------------- #
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)

            if path == "/":
                index = WEB_DIR / "index.html"
                if not index.exists():
                    self._json(500, {"error": "Thiếu file web/index.html"})
                    return
                self._send(200, index.read_bytes(), "text/html; charset=utf-8")
                return

            if path == "/api/health":
                self._json(200, {
                    "status": "healthy",
                    "version": "1.0.0",
                    "uptime_s": round(time.time() - _START_TIME, 1),
                    "store": agent.store.stats(),
                })
                return

            if path == "/api/status":
                self._json(200, agent.state.snapshot())
                return

            if path == "/api/metrics":
                snapshot = agent.state.snapshot()
                payload = dict(snapshot["status"])
                payload["metrics"] = snapshot["latest"]
                payload["meter_id"] = agent.config.meter_id
                payload["rack_id"] = agent.config.rack_id
                payload["simulate"] = payload.get("port") == "SIMULATED"
                self._json(200, payload)
                return

            if path == "/api/history":
                since = _float(query.get("from", [None])[0])
                until = _float(query.get("to", [None])[0])
                resolution = query.get("resolution", ["raw"])[0]
                limit = int(_float(query.get("limit", [5000])[0]) or 5000)
                rows = agent.store.query_history(
                    meter_id=agent.config.meter_id,
                    since=since,
                    until=until,
                    resolution=resolution,
                    limit=limit,
                )
                self._json(200, {"resolution": resolution, "count": len(rows), "rows": rows})
                return

            if path == "/api/events":
                active_only = query.get("active_only", ["false"])[0].lower() in ("1", "true", "yes")
                limit = int(_float(query.get("limit", [100])[0]) or 100)
                rows = agent.store.query_events(active_only=active_only, limit=limit)
                self._json(200, {"count": len(rows), "rows": rows})
                return

            if path == "/api/config":
                self._json(200, {
                    "meter_id": agent.config.meter_id,
                    "rack_id": agent.config.rack_id,
                    "site_id": agent.config.site_id,
                    "port": agent.config.port,
                    "usb_location": agent.config.usb_location,
                    "slave_address": agent.config.slave_address,
                    "baudrate": agent.config.baudrate,
                    "poll_interval_s": agent.config.poll_interval_s,
                    "power_threshold_w": agent.config.power_threshold_w,
                    "voltage_min_v": agent.config.voltage_min_v,
                    "voltage_max_v": agent.config.voltage_max_v,
                    "auth_required": bool(agent.config.api_token),
                })
                return

            self._json(404, {"error": "Not found"})

    return AgentHandler


def _float(value) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


_START_TIME = time.time()
