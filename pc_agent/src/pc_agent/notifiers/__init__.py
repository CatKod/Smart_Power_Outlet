"""Gửi thông báo tổng hợp khi có sự kiện mức `critical` (A-7-7).

Vì sao cần:
  - PC Agent chạy trong tủ rack, không ai nhìn màn hình lúc 3h sáng.
  - Khi quá tải hoặc mất kết nối, cần biết **ngay**.

Nguyên tắc thiết kế quan trọng:
  - **Agent KHÔNG BAO GIỜ chết vì thông báo lỗi.** Nếu webhook chậm, DNS lỗi
    hoặc mạng mất, agent vẫn phải tiếp tục giám sát.
  - Vì vậy thông báo được đẩy vào **queue** và gửi bởi **thread riêng**.
    Thread gửi bị treo cũng không ảnh hưởng vòng lấy mẫu 1 Hz.
  - Queue có giới hạn số phần tử → nếu mạng chết lâu, hàng đợi đầy thì **xoá
    bản cũ** (giữ bản mới nhất) thay vì nhớ vô hạn và làm rò rỉ bộ nhớ.

Cơ chế hiện thực:
  - `TelegramNotifier` dùng HTTPS POST tới Bot API (stdlib `urllib` — không
    thêm dependency).
  - `Notifier` là interface → dễ thêm email/Slack/Pushover sau này.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional, Protocol

LOG = logging.getLogger("pc_agent.notifiers")

# Kích thước tối đa của hàng đợi. Khi đầy → drop bản cũ (giữ bản mới).
QUEUE_MAXSIZE = 100

# Timeout cho một lần gọi HTTP (giây).
HTTP_TIMEOUT_S = 5.0

# Số lần thử lại khi gửi thất bại.
MAX_RETRIES = 2


# --------------------------------------------------------------------------- #
class Notifier(Protocol):
    """Interface của một kênh thông báo."""

    name: str

    def send(self, title: str, message: str, severity: str = "critical") -> bool:
        """Gửi thông báo. Trả `True` nếu thành công."""
        ...


# --------------------------------------------------------------------------- #
class TelegramNotifier:
    """Gửi thông báo qua Telegram Bot API.

    Cấu hình (biến môi trường — **không** hardcode trong mã nguồn):
      - `PC_AGENT_TELEGRAM_TOKEN` : `<bot_id>:<bot_token>`
      - `PC_AGENT_TELEGRAM_CHAT_ID` : id chat nhận thông báo
    """

    name = "telegram"

    def __init__(
        self,
        token: Optional[str] = None,
        chat_id: Optional[str] = None,
        timeout: float = HTTP_TIMEOUT_S,
    ) -> None:
        import os

        self.token = token or os.environ.get("PC_AGENT_TELEGRAM_TOKEN", "")
        self.chat_id = chat_id or os.environ.get("PC_AGENT_TELEGRAM_CHAT_ID", "")
        self.timeout = timeout

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.chat_id)

    def send(self, title: str, message: str, severity: str = "critical") -> bool:
        if not self.enabled:
            LOG.debug("Telegram chưa được cấu hình — bỏ qua thông báo.")
            return False

        # Telegram giới hạn 4096 ký tự mỗi tin; cắt bớt phần message dài.
        text = f"[{severity.upper()}] {title}\n\n{message}"
        if len(text) > 4000:
            text = text[:3990] + "…"

        payload = urllib.parse.urlencode(
            {
                "chat_id": self.chat_id,
                "text": text,
                "disable_notification": "false",
            }
        ).encode("utf-8")

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                req = urllib.request.Request(
                    url, data=payload, method="POST",
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    body = resp.read().decode("utf-8", "replace")
                    if resp.status == 200:
                        return True
                    LOG.warning("Telegram trả về HTTP %s: %s", resp.status, body[:200])
            except urllib.error.HTTPError as exc:
                # 4xx (trừ 429) là lỗi cấu hình → không thử lại.
                if exc.code < 500 and exc.code != 429:
                    LOG.error("Telegram từ chối yêu cầu (HTTP %s) — kiểm tra bot token/chat id.",
                              exc.code)
                    return False
                LOG.warning("Telegram lỗi HTTP %s (lần %d/%d)", exc.code, attempt, MAX_RETRIES)
            except (urllib.error.URLError, OSError) as exc:
                LOG.warning("Không gửi được thông báo Telegram: %s (lần %d/%d)",
                            exc, attempt, MAX_RETRIES)

        return False


# --------------------------------------------------------------------------- #
class NotifierDispatcher:
    """Hàng đợi + thread gửi nền.

    `notify()` chỉ đẩy vào queue và trả về ngay — **không** bao giờ block hay
    raise ra ngoài. Lỗi trong thread gửi chỉ được ghi log.
    """

    def __init__(self, notifiers: Optional[list] = None) -> None:
        self.notifiers = list(notifiers or [])
        self._queue: "queue.Queue[Dict[str, Any]]" = queue.Queue(
            maxsize=QUEUE_MAXSIZE
        )
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._sent = 0
        self._failed = 0
        self._dropped = 0
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ #
    def start(self) -> None:
        if not self.notifiers:
            return
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, name="NotifierDispatcher", daemon=True
        )
        self._thread.start()
        LOG.info(
            "Đã bật %d kênh thông báo: %s",
            len(self.notifiers), ", ".join(n.name for n in self.notifiers),
        )

    def stop(self, timeout: float = 3.0) -> None:
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        self._thread = None

    # ------------------------------------------------------------------ #
    def notify(self, title: str, message: str, severity: str = "critical") -> None:
        """Đẩy thông báo vào hàng đợi. **Không** bao giờ raise hay block lâu."""
        if not self.notifiers:
            return
        item = {"title": title, "message": message, "severity": severity}
        try:
            self._queue.put_nowait(item)
        except queue.Full:
            # Hàng đợi đầy (mạng chết lâu) → bỏ bản cũ nhất, giữ bản mới.
            with self._lock:
                self._dropped += 1
            try:
                self._queue.get_nowait()
                self._queue.task_done()
                self._queue.put_nowait(item)
            except (queue.Empty, queue.Full):
                pass
            LOG.warning("Hàng đợi thông báo đầy — đã bỏ bản cũ nhất.")

    # ------------------------------------------------------------------ #
    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                item = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            try:
                self._dispatch(item)
            except Exception as exc:  # noqa: BLE001 - thread nền không được chết
                LOG.error("Lỗi khi gửi thông báo: %s", exc)
            finally:
                self._queue.task_done()

    def _dispatch(self, item: Dict[str, Any]) -> None:
        for notifier in self.notifiers:
            try:
                ok = notifier.send(
                    item["title"], item["message"], item.get("severity", "critical")
                )
                with self._lock:
                    if ok:
                        self._sent += 1
                    else:
                        self._failed += 1
            except Exception as exc:  # noqa: BLE001
                LOG.error("Kênh %s lỗi: %s", getattr(notifier, "name", "?"), exc)
                with self._lock:
                    self._failed += 1

    # ------------------------------------------------------------------ #
    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "enabled": bool(self.notifiers),
                "channels": [n.name for n in self.notifiers],
                "sent": self._sent,
                "failed": self._failed,
                "dropped": self._dropped,
                "queued": self._queue.qsize(),
            }


# --------------------------------------------------------------------------- #
def build_default_dispatcher() -> NotifierDispatcher:
    """Tạo dispatcher với các kênh thông báo được cấu hình qua biến môi trường."""
    notifiers = []
    telegram = TelegramNotifier()
    if telegram.enabled:
        notifiers.append(telegram)
    return NotifierDispatcher(notifiers)
