"""Quản lý token xác thực API (A-8-6).

Vì sao cần module này?
  - PC Agent mặc định bind `127.0.0.1` → chỉ máy chủ rack truy cập được.
  - Khi ai đó mở ra LAN (`--host 0.0.0.0`) thì **bắt buộc** phải có xác thực.
    Trước đây `api_token=None` ⇒ API không có cửa nào chắn → lỗ hổng.
  - Nguyên tắc: **không bao giờ** khởi động được với bind ngoài localhost mà
    không có token. Nếu không tạo/lấy được token thì **từ chối khởi động**
    (fail-closed), thay vì chạy với API mở toang.

So sánh token dùng `hmac.compare_digest` — chống timing attack (so sánh
thời gian của `==` leak độ dài/độ trùng của chuỗi tiền tố).

Nơi lưu token:
  - `config.json` (`api_token`) — thuận tiện cho `ConfigStore`;
  - `api_token.txt` — bản sao chỉ-đọc cho người vận hành, tự sinh nếu thiếu.

Token **không** được ghi vào log ở mức INFO quá 1 lần duy nhất khi khởi tạo;
sau đó chỉ in *đường dẫn file* để người vận hành tự mở.
"""

from __future__ import annotations

import hmac
import logging
import os
import secrets
import stat
from pathlib import Path
from typing import Optional

LOG = logging.getLogger("pc_agent.auth")

TOKEN_BYTES = 32          # 32 byte ngẫu nhiên -> 43 ký tự base64url
TOKEN_FILENAME = "api_token.txt"

# Các địa chỉ loopback — bind vào đây thì không bắt buộc xác thực.
_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost", ""}


def is_loopback(host: Optional[str]) -> bool:
    """`host` có phải loopback không?

    `0.0.0.0` và `::` **không** phải loopback — chúng nghe trên mọi giao diện
    mạng, nên bắt buộc phải có token.
    """
    if host is None:
        return True
    h = host.strip().lower()
    if h in _LOOPBACK_HOSTS:
        return True
    # 127.x.x.x — toàn bộ dải loopback của IPv4
    return h.startswith("127.")


def generate_token() -> str:
    """Sinh token ngẫu nhiên (URL-safe, đủ dài để không đoán được)."""
    return secrets.token_urlsafe(TOKEN_BYTES)


def token_file_path(config_dir: Path) -> Path:
    return Path(config_dir) / TOKEN_FILENAME


def write_token_file(path: Path, token: str) -> bool:
    """Ghi token ra file với quyền hạn chế (chỉ owner đọc được).

    Trên Windows, `os.chmod` chỉ đặt được cờ read-only — không thực sự giống
    Unix. Vì vậy ta **không** phụ thuộc vào chmod để bảo mật; token vẫn nằm
    trong `%ProgramData%` (mặc định chỉ Administrators/SYSTEM ghi được).
    """
    path = Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Ghi atomically để không để lại file 0 byte nếu mất điện giữa lúc ghi.
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(token + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        try:
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
        return True
    except OSError as exc:
        LOG.error("Không ghi được file token %s: %s", path, exc)
        return False


def read_token_file(path: Path) -> Optional[str]:
    """Đọc token từ file. Trả `None` nếu không có hoặc không đọc được."""
    path = Path(path)
    try:
        content = path.read_text(encoding="utf-8").strip()
        return content or None
    except OSError:
        return None


def verify_token(expected: Optional[str], provided: Optional[str]) -> bool:
    """Kiểm tra token có khớp không.

    - `expected` rỗng/None → **cho qua** (chỉ dùng khi bind loopback).
    - So sánh bằng `hmac.compare_digest` để không rò rỉ thông tin qua thời gian.
    """
    if not expected:
        return True
    if not provided:
        return False
    return hmac.compare_digest(str(expected), str(provided))


def ensure_token(
    config,
    config_store=None,
    force_new: bool = False,
) -> Optional[str]:
    """Đảm bảo có token hợp lệ theo chính sách bind.

    Trả về token đang dùng, hoặc `None` nếu không thể đảm bảo an toàn.

    Chính sách:
      1. Bind loopback → token không bắt buộc; nếu đã có thì giữ nguyên.
      2. Bind ngoài localhost → **bắt buộc** có token.
         - Nếu `force_new` → sinh token mới.
         - Nếu `config.api_token` đã có → dùng lại, đồng thời đảm bảo file
           `api_token.txt` khớp (để người vận hành có nơi lấy token).
         - Nếu chưa có → thử đọc từ `api_token.txt`; nếu file có token hợp lệ
           thì dùng và lưu vào config.
         - Nếu vẫn chưa có → sinh token mới, lưu vào config **và** file.
      3. Ghi config/DB thất bại → trả `None` (fail-closed) để caller từ chối
         khởi động, thay vì chạy với API mở không xác thực.
    """
    from .config import config_dir

    if is_loopback(config.api_host) and not force_new:
        # Vẫn ghi file token nếu đã có, để thao tác vận hành thống nhất.
        if config.api_token:
            write_token_file(token_file_path(config_dir()), config.api_token)
        return config.api_token

    if force_new:
        token = generate_token()
        LOG.info("Đã sinh token API mới theo yêu cầu (--rotate-token).")
    elif config.api_token:
        token = config.api_token
    else:
        token = read_token_file(token_file_path(config_dir()))
        if token:
            LOG.info("Đã khôi phục token API từ %s", token_file_path(config_dir()))
        else:
            token = generate_token()
            LOG.info("Đã sinh token API mới (bind ngoài localhost — bắt buộc xác thực).")

    if not token:
        LOG.error("Không tạo được token API — từ chối khởi động ở chế độ mở mạng.")
        return None

    # Ghi ra file để người vận hành lấy được (không in token ra log).
    if not write_token_file(token_file_path(config_dir()), token):
        LOG.error("Không ghi được file token — từ chối khởi động ở chế độ mở mạng.")
        return None

    # Lưu vào config để giữ token qua các lần khởi động lại.
    if config.api_token != token:
        config.api_token = token
        if config_store is not None:
            try:
                config_store.save(config)
            except Exception as exc:  # noqa: BLE001
                LOG.error("Không lưu được token vào cấu hình: %s", exc)
                return None

    LOG.warning(
        "API đang lắng nghe trên %s — BẮT BUỘC xác thực. "
        "Đọc token tại: %s",
        config.api_host, token_file_path(config_dir()),
    )
    return token
