"""Thiết lập logging an toàn cho môi trường service (Session 0).

Vấn đề cốt lõi: một Windows Service chạy ở **Session 0** — không có console.
Trong trường hợp đó `sys.stdout` / `sys.stderr` có thể là `None` hoặc trỏ tới
handle không hợp lệ, khiến `logging.StreamHandler` ném `AttributeError` /
`OSError: [WinError 6] The handle is invalid` và làm sập tiến trình service.

Vì vậy:
  - **luôn** ghi log ra file (xoay vòng theo kích thước);
  - chỉ gắn thêm handler tới console khi console thực sự dùng được;
  - dùng `RotatingFileHandler` chứ không phải `TimedRotatingFileHandler` để
    tránh rủi ro xoay file khi service đang bị kill giữa chừng.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from pathlib import Path
from typing import Optional

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

MAX_BYTES = 10 * 1024 * 1024
BACKUP_COUNT = 10


def setup_logging(
    log_dir: Optional[Path] = None,
    level: int = logging.INFO,
    console: Optional[bool] = None,
) -> Path:
    """Cấu hình logging và trả về thư mục log đã dùng."""
    if log_dir is None:
        from ..config import log_dir as default_log_dir
        log_dir = default_log_dir()

    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "agent.log"

    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)
    root = logging.getLogger()
    root.setLevel(level)
    for handler in list(root.handlers):
        root.removeHandler(handler)

    # --- Handler file: luôn có, kể cả Session 0 ---
    try:
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=MAX_BYTES,
            backupCount=BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except OSError as exc:
        # Không tạo được file log vẫn phải chạy được — chỉ mất log file.
        print(f"Không mở được file log {log_file}: {exc}", file=sys.stderr)

    # --- Handler console: chỉ khi thực sự chạy foreground ---
    if console is None:
        console = _console_available()
    if console:
        stream = logging.StreamHandler(sys.stdout)
        stream.setFormatter(formatter)
        root.addHandler(stream)

    return log_dir


def _console_available() -> bool:
    """Kiểm tra stdout còn dùng được không (Session 0 thường không)."""
    if os.environ.get("SMARTPOWER_FORCE_CONSOLE"):
        return True
    for stream in (sys.stdout, sys.stderr):
        if stream is None:
            return False
        try:
            stream.write("")
            stream.flush()
        except Exception:  # noqa: BLE001
            return False
    return True


def redirect_std_streams_to_devnull() -> None:
    """Chuyển stdout/stderr về null device.

    Dùng khi chạy dưới một service wrapper không thu được stdout (ví dụ NSSM
    mà không cấu hình `AppStdout`). Tránh mọi `print()` ném exception trong
    Session 0.
    """
    devnull = open(os.devnull, "w", encoding="utf-8")
    sys.stdout = devnull
    sys.stderr = devnull
