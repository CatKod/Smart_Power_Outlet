"""Trạng thái số liệu trực tiếp, dùng chung giữa luồng đọc và API.

Một `StateStore` duy nhất giữ:
  - mẫu đo mới nhất (để API trả về tức thì, không cần đọc DB),
  - trạng thái kết nối / lỗi cuối cùng,
  - bộ đếm mẫu.

Tất cả truy cập đều qua `threading.Lock` — API chạy ở thread HTTP, còn luồng
đọc chạy ở thread riêng.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class DeviceStatus:
    """Trạng thái hiện tại của thiết bị đo."""

    connected: bool = False
    port: Optional[str] = None
    address: Optional[int] = None
    error: Optional[str] = None
    samples: int = 0
    last_update: Optional[float] = None
    last_error: Optional[float] = None
    consecutive_errors: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "connected": self.connected,
            "port": self.port,
            "address": self.address,
            "error": self.error,
            "samples": self.samples,
            "last_update": self.last_update,
            "last_error": self.last_error,
            "consecutive_errors": self.consecutive_errors,
        }


class StateStore:
    """Kho trạng thái dùng chung, an toàn khi đọc/ghi từ nhiều thread."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._latest: Optional[Dict[str, Any]] = None
        self._status = DeviceStatus()

    # -- trạng thái -------------------------------------------------------- #
    def set_connected(self, connected: bool, error: Optional[str] = None) -> None:
        with self._lock:
            self._status.connected = connected
            if error is not None:
                self._status.error = error
                self._status.last_error = time.time()
            if connected:
                self._status.error = None
                self._status.consecutive_errors = 0

    def set_port(self, port: Optional[str], address: Optional[int]) -> None:
        with self._lock:
            self._status.port = port
            self._status.address = address

    def set_error(self, error: str) -> None:
        with self._lock:
            self._status.connected = False
            self._status.error = error
            self._status.last_error = time.time()
            self._status.consecutive_errors += 1

    def set_sample(self, sample: Dict[str, Any]) -> None:
        with self._lock:
            self._latest = sample
            self._status.samples += 1
            self._status.last_update = sample.get("timestamp", time.time())
            self._status.connected = True
            self._status.error = None
            self._status.consecutive_errors = 0

    # -- đọc -------------------------------------------------------------- #
    @property
    def latest(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            return dict(self._latest) if self._latest else None

    @property
    def status(self) -> DeviceStatus:
        with self._lock:
            return DeviceStatus(**self._status.to_dict())

    def snapshot(self) -> Dict[str, Any]:
        """Ảnh chụp toàn bộ trạng thái (dùng cho API)."""
        with self._lock:
            return {
                "status": self._status.to_dict(),
                "latest": dict(self._latest) if self._latest else None,
            }
