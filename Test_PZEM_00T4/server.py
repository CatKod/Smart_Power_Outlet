"""
Web server hiển thị các thông số đo được từ PZEM-004T.

- Một luồng nền đọc PZEM liên tục (mặc định 1 Hz) và cập nhật trạng thái.
- Giao diện web tại  http://127.0.0.1:8000/
- API JSON tại     /api/metrics
- Có thể đổi cổng serial / địa chỉ slave bằng tham số dòng lệnh.

Ví dụ:
    python server.py --port COM10
    python server.py --port COM10 --address 1 --baud 9600
    python server.py --simulate          # chạy thử không cần phần cứng
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))

from pzem004t import Pzem004T, PzemError  # noqa: E402

LOG = logging.getLogger("pzem-web")

WEB_DIR = Path(__file__).parent / "web"

# --- Trạng thái chia sẻ giữa luồng đọc và luồng web --- #
_lock = threading.Lock()
_latest: Optional[dict] = None
_error: Optional[str] = None
_connected: bool = False
_samples: int = 0
_last_ok_ts: Optional[float] = None

_config = {
    "port": "COM10",
    "baud": 9600,
    "address": 0xF8,
    "interval": 1.0,
    "simulate": False,
}


# --------------------------------------------------------------------------- #
# Chế độ mô phỏng (dùng để kiểm thử giao diện khi chưa nối được phần cứng)
# --------------------------------------------------------------------------- #
def simulate_metrics(t: float) -> dict:
    """Sinh dữ liệu giả lập theo hình sin để kiểm thử giao diện."""
    voltage = 220.0 + math.sin(t / 3.0) * 2.5
    current = 1.25 + math.sin(t / 2.0) * 0.5
    power_factor = 0.95
    power = voltage * current * power_factor
    energy_wh = 1234.0 + t * power / 3600.0
    return {
        "voltage": round(voltage, 1),
        "current": round(current, 3),
        "power": round(power, 1),
        "energy": round(energy_wh, 0),
        "energy_kwh": round(energy_wh / 1000.0, 3),
        "frequency": round(50.0 + math.sin(t / 5.0) * 0.15, 1),
        "power_factor": round(power_factor, 2),
        "alarm": 0,
        "timestamp": time.time(),
    }


# --------------------------------------------------------------------------- #
# Luồng nền đọc PZEM
# --------------------------------------------------------------------------- #
def pzem_worker(stop_event: threading.Event) -> None:
    """Giữ kết nối serial và cập nhật trạng thái toàn cục mỗi chu kỳ."""
    global _latest, _error, _connected, _samples, _last_ok_ts

    if _config["simulate"]:
        _run_simulator(stop_event)
        return

    while not stop_event.is_set():
        try:
            # Mở phiên serial dùng chung (khoá ở cấp hàm, không khoá lồng)
            with _serial_lock:
                pzem = _get_session()

            LOG.info(
                "Đã mở cổng %s (addr 0x%02X, %d baud)",
                _config["port"], _config["address"], _config["baud"],
            )

            while not stop_event.is_set():
                try:
                    with _serial_lock:
                        metrics = pzem.read()
                except PzemError as exc:
                    _set_state(error=str(exc), connected=False)
                    LOG.warning("Lỗi đọc PZEM: %s", exc)
                    break
                except Exception as exc:  # noqa: BLE001
                    _set_state(error=f"Lỗi không mong đợi: {exc}", connected=False)
                    LOG.exception("Lỗi không mong đợi khi đọc PZEM")
                    break

                data = metrics.to_dict()
                with _lock:
                    _latest = data
                    _error = None
                    _connected = True
                    _samples += 1
                    _last_ok_ts = time.time()
                stop_event.wait(_config["interval"])
        except PzemError as exc:
            _set_state(error=str(exc), connected=False)
            LOG.warning("Chưa kết nối được PZEM: %s", exc)
            stop_event.wait(3.0)
            continue
        except Exception as exc:  # noqa: BLE001
            _set_state(error=f"Lỗi không mong đợi: {exc}", connected=False)
            LOG.exception("Lỗi không mong đợi")
            stop_event.wait(3.0)
            continue
        finally:
            with _serial_lock:
                _close_session()

        _set_state(connected=False)
        # Backoff: không thử lại liên tục, tránh spam log và giữ CPU
        stop_event.wait(3.0)

    with _serial_lock:
        _close_session()


def _run_simulator(stop_event: threading.Event) -> None:
    global _latest, _error, _connected, _samples, _last_ok_ts
    start = time.time()
    _set_state(error=None, connected=True)
    while not stop_event.is_set():
        data = simulate_metrics(time.time() - start)
        with _lock:
            _latest = data
            _error = None
            _connected = True
            _samples += 1
            _last_ok_ts = time.time()
        stop_event.wait(_config["interval"])
    _set_state(connected=False)


def _set_state(error: Optional[str] = None, connected: Optional[bool] = None) -> None:
    global _error, _connected
    with _lock:
        if error is not None:
            _error = error
        if connected is not None:
            _connected = connected


# --------------------------------------------------------------------------- #
# Phiên serial dùng chung
#
# Worker nền và các API scan/settings đều cần truy cập cổng serial, nhưng
# Windows không cho mở cùng một cổng ở hai chỗ. Vì vậy chỉ có MỘT đối tượng
# Pzem004T dùng chung, bảo vệ bằng mutex.
# --------------------------------------------------------------------------- #
_serial_lock = threading.Lock()
_session: Optional[Pzem004T] = None


def _get_session() -> Pzem004T:
    """Trả về phiên serial dùng chung (đã mở)."""
    global _session
    if _session is None:
        _session = Pzem004T(
            port=_config["port"],
            baudrate=_config["baud"],
            address=_config["address"],
            timeout=1.0,
        )
        _session.open()
    return _session


def _close_session() -> None:
    global _session
    if _session is not None:
        _session.close()
        _session = None


def _with_session(action):
    """Chạy `action(session)` dưới khoá serial, tự mở/đóng khi cần."""
    with _serial_lock:
        try:
            session = _get_session()
        except PzemError as exc:
            return f"Lỗi: {exc}"
        except Exception as exc:  # noqa: BLE001
            return f"Lỗi: {exc}"
        try:
            return action(session)
        except PzemError as exc:
            return f"Lỗi: {exc}"
        except Exception as exc:  # noqa: BLE001
            return f"Lỗi: {exc}"


# --------------------------------------------------------------------------- #
# HTTP handler
# --------------------------------------------------------------------------- #
class PzemHandler(BaseHTTPRequestHandler):
    server_version = "PzemWeb/1.0"

    def log_message(self, fmt, *args):  # noqa: A003
        LOG.debug("%s - %s", self.address_string(), fmt % args)

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]

        if path == "/":
            index = WEB_DIR / "index.html"
            if not index.exists():
                self._json(500, {"error": "Thiếu file web/index.html"})
                return
            self._send(200, index.read_bytes(), "text/html; charset=utf-8")
            return

        if path == "/api/metrics":
            with _lock:
                payload = {
                    "connected": _connected,
                    "error": _error,
                    "samples": _samples,
                    "last_update": _last_ok_ts,
                    "port": "COM10" if _config["simulate"] else _config["port"],
                    "baud": _config["baud"],
                    "address": _config["address"],
                    "simulate": _config["simulate"],
                    "metrics": _latest,
                }
            self._json(200, payload)
            return

        if path == "/api/scan":
            self._json(200, {"result": self._do_scan()})
            return

        if path == "/api/settings":
            self._json(200, {"result": self._do_settings()})
            return

        self._json(404, {"error": "Not found"})

    # -- tác vụ bảo trì ------------------------------------------------- #
    def _do_scan(self) -> str:
        """Dò xem địa chỉ slave nào phản hồi."""
        if _config["simulate"]:
            return "Chế độ mô phỏng - không có thiết bị thật để dò"

        def action(session):
            found = session.scan_addresses()
            if not found:
                return (
                    "Không slave nào phản hồi. Nhớ cấp nguồn lưới AC 220V cho PZEM "
                    "(chân L/N) và kiểm tra dây TX/RX."
                )
            return "Phản hồi: " + ", ".join(f"0x{a:02X}" for a in found)
        return _with_session(action)

    def _do_settings(self) -> str:
        """Đọc tham số slave (ngưỡng cảnh báo, địa chỉ)."""
        if _config["simulate"]:
            return "Chế độ mô phỏng - không có thiết bị thật"

        def action(session):
            info = session.read_settings()
            return (
                f"địa chỉ slave=0x{info['slave_address']:02X}, "
                f"ngưỡng cảnh báo={info['power_alarm_threshold']} W"
            )

        return _with_session(action)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Web hiển thị thông số PZEM-004T")
    p.add_argument("--port", default="COM10", help="Cổng serial của TTL-USB (mặc định COM10)")
    p.add_argument("--baud", type=int, default=9600, help="Tốc độ baud (mặc định 9600)")
    p.add_argument(
        "--address",
        type=lambda s: int(s, 0),
        default=0xF8,
        help="Địa chỉ Modbus slave (mặc định 0xF8 - địa chỉ chung)",
    )
    p.add_argument("--web-port", type=int, default=8000, help="Cổng web server (mặc định 8000)")
    p.add_argument("--host", default="127.0.0.1", help="Địa chỉ lắng nghe (mặc định 127.0.0.1)")
    p.add_argument("--interval", type=float, default=1.0, help="Chu kỳ lấy mẫu (giây)")
    p.add_argument(
        "--simulate",
        action="store_true",
        help="Chạy chế độ mô phỏng (không cần phần cứng)",
    )
    return p.parse_args(argv)


def main(argv=None) -> int:
    global _config

    args = parse_args(argv)
    _config = {
        "port": args.port,
        "baud": args.baud,
        "address": args.address,
        "interval": args.interval,
        "simulate": args.simulate,
    }

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    os.chdir(Path(__file__).parent)

    stop_event = threading.Event()
    worker = threading.Thread(target=pzem_worker, args=(stop_event,), daemon=True)
    worker.start()

    httpd = ThreadingHTTPServer((args.host, args.web_port), PzemHandler)
    LOG.info("Mở trang web tại http://%s:%d/", args.host, args.web_port)
    if args.simulate:
        LOG.info("Chế độ mô phỏng - không đọc phần cứng thật")
    else:
        LOG.info(
            "Đang đọc PZEM-004T trên %s @ %d baud, địa chỉ slave 0x%02X",
            args.port, args.baud, args.address,
        )

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        LOG.info("Đang dừng...")
    finally:
        stop_event.set()
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
