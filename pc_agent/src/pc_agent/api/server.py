"""API HTTP của PC Agent.

Dùng `http.server` chuẩn của Python (không thêm framework) để giữ phụ thuộc
tối thiểu — đây là service chạy 24/7 trên máy chủ, mỗi dependency là một
rủi ro bảo mật và cập nhật.

Ràng buộc bảo mật (A-8-6):
  - mặc định chỉ bind `127.0.0.1`;
  - khi bind **ngoài** localhost, xác thực là **bắt buộc** — token được sinh
    tự động ở `pc_agent.auth` và so sánh bằng `hmac.compare_digest`;
  - endpoint đọc (`/api/status`, `/api/metrics`, `/api/history`, `/api/events`,
    `/api/config`) yêu cầu token khi API mở ra mạng;
  - `/api/health` là **công khai** — chỉ báo "còn sống hay không", không chứa
    dữ liệu nhạy cảm. Cần cho monitor (systemd watchdog, Uptime Kuma) không
    phải giữ token;
  - mọi endpoint `POST` (thay đổi trạng thái) **luôn** yêu cầu token, kể cả
    khi bind loopback.
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

from ..auth import is_loopback, verify_token
from ..version import version_info

LOG = logging.getLogger("pc_agent.api")

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

# Endpoint không cần xác thực.
PUBLIC_ENDPOINTS = frozenset({"/api/health"})


class AgentServer:
    """Bọc `ThreadingHTTPServer` thành đối tượng có thể start/stop."""

    def __init__(
        self,
        config,
        state,
        store,
        host: Optional[str] = None,
        port: Optional[int] = None,
        config_store=None,
    ) -> None:
        self.config = config
        self.state = state
        self.store = store
        self.host = host if host is not None else config.api_host
        self.port = port if port is not None else config.api_port
        self.config_store = config_store
        self._httpd: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._config_lock = threading.Lock()

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

    # ------------------------------------------------------------------ #
    def public_config(self) -> Dict[str, Any]:
        """Cấu hình có thể trả về cho client (không chứa bí mật)."""
        return {
            "meter_id": self.config.meter_id,
            "rack_id": self.config.rack_id,
            "site_id": self.config.site_id,
            "port": self.config.port,
            "usb_location": self.config.usb_location,
            "slave_address": self.config.slave_address,
            "baudrate": self.config.baudrate,
            "poll_interval_s": self.config.poll_interval_s,
            "power_threshold_w": self.config.power_threshold_w,
            "current_threshold_a": self.config.current_threshold_a,
            "voltage_min_v": self.config.voltage_min_v,
            "voltage_max_v": self.config.voltage_max_v,
            "auth_required": bool(self.config.api_token),
        }

    # ------------------------------------------------------------------ #
    def update_config(self, payload: Dict[str, Any]) -> list:
        """Cập nhật một số tham số cấu hình cho phép.

        Chỉ cho sửa **ngưỡng cảnh báo** và **chu kỳ lấy mẫu** — không cho đổi
        cổng serial hay địa chỉ slave từ xa (đó là việc của discovery).
        """
        allowed = {
            "power_threshold_w": int,
            "current_threshold_a": float,
            "voltage_min_v": float,
            "voltage_max_v": float,
            "poll_interval_s": float,
            "offline_after_s": float,
        }
        changed: list = []
        with self._config_lock:
            for key, caster in allowed.items():
                if key not in payload:
                    continue
                try:
                    value = caster(payload[key])
                except (TypeError, ValueError):
                    LOG.warning("Bỏ qua giá trị không hợp lệ cho %s: %r", key, payload[key])
                    continue
                if getattr(self.config, key) != value:
                    setattr(self.config, key, value)
                    changed.append(key)

            if changed and self.config_store is not None:
                try:
                    self.config_store.save(self.config)
                except Exception as exc:  # noqa: BLE001
                    LOG.error("Không lưu được cấu hình mới: %s", exc)
        if changed:
            LOG.info("Đã cập nhật cấu hình: %s", ", ".join(changed))
        return changed

    # ------------------------------------------------------------------ #
    def rotate_token(self) -> Optional[str]:
        """Sinh token API mới và lưu lại (dùng khi nghi ngờ bị lộ)."""
        from ..auth import ensure_token

        with self._config_lock:
            return ensure_token(self.config, self.config_store, force_new=True)


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

        def _authorized(self, query: Optional[Dict] = None) -> bool:
            """Kiểm tra Bearer token nếu API được mở ra ngoài localhost.

            Khi bind loopback → không cần token (chỉ máy chủ rack truy cập).
            Khi bind ngoài localhost → token là **bắt buộc**; nếu vì lý do gì
            đó `api_token` lại rỗng thì **từ chối** (fail-closed) chứ không
            mở API không có cửa.

            Ngoài header `Authorization`, chấp nhận thêm token trong query
            string (`?token=...`) để mở được dashboard bằng link:
            `http://host:8000/?token=xxx`. Việc này **chỉ** dành cho GET —
            không có tác dụng với POST (mọi thao tác ghi vẫn phải dùng header).
            """
            token = agent.config.api_token
            if not token:
                # Chỉ chấp nhận khi API thực sự chỉ nghe loopback.
                return is_loopback(agent.host)

            provided = None
            header = self.headers.get("Authorization", "")
            if header.startswith("Bearer "):
                provided = header.split("Bearer ", 1)[1].strip()
            elif query:
                values = query.get("token")
                if values:
                    provided = values[0].strip()
            return verify_token(token, provided)

        def _guard(self, path: str, query: Optional[Dict] = None) -> bool:
            """Kiểm tra xác thực cho GET. Trả `False` nếu đã trả lỗi 401."""
            if path in PUBLIC_ENDPOINTS:
                return True
            if self._authorized(query):
                return True
            self._json(401, {
                "error": "Unauthorized",
                "detail": (
                    "API đang lắng nghe ngoài localhost — cần header "
                    "'Authorization: Bearer <token>' hoặc tham số '?token=...'. "
                    "Đọc token tại file api_token.txt trong thư mục cấu hình."
                ),
            })
            return False

        # -- routes ------------------------------------------------------- #
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)

            if not self._guard(path, query):
                return

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
                    "uptime_s": round(time.time() - _START_TIME, 1),
                    "store": agent.store.stats(),
                    **version_info(),
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
                limit = int(_float(query.get("limit", ["5000"])[0]) or 5000)
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
                limit = int(_float(query.get("limit", ["100"])[0]) or 100)
                rows = agent.store.query_events(active_only=active_only, limit=limit)
                self._json(200, {"count": len(rows), "rows": rows})
                return

            if path == "/api/config":
                self._json(200, agent.public_config())
                return

            self._json(404, {"error": "Not found"})

        # -- ghi ------------------------------------------------------------ #
        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path

            # Mọi endpoint POST đều yêu cầu token, kể cả khi bind loopback —
            # đây là endpoint thay đổi trạng thái.
            if not self._authorized():
                self._json(401, {"error": "Unauthorized"})
                return

            length = int(self.headers.get("Content-Length", "0") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw.decode("utf-8") or "{}")
            except (ValueError, UnicodeDecodeError):
                self._json(400, {"error": "Body không phải JSON hợp lệ"})
                return
            if not isinstance(payload, dict):
                self._json(400, {"error": "Body phải là JSON object"})
                return

            if path == "/api/config":
                changed = agent.update_config(payload)
                self._json(200, {
                    "ok": True,
                    "changed": changed,
                    "config": agent.public_config(),
                })
                return

            if path == "/api/config/token":
                new_token = agent.rotate_token()
                if new_token is None:
                    self._json(500, {"error": "Không tạo được token mới"})
                    return
                self._json(200, {
                    "ok": True,
                    "detail": "Token đã đổi. Đọc token mới tại file api_token.txt",
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
