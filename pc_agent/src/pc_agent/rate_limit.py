"""Giới hạn tốc độ log khi lỗi lặp (A-9-2).

Vấn đề: PC Agent lấy mẫu mỗi 1 giây. Nếu cổng serial hỏng, mỗi vòng lấy
mẫu lại log một lần → 86 400 dòng log/ngày → đầy ổ đĩa, và log trở nên vô
dụng vì bị chôn vùi trong dòng lặp.

Cơ chế: **suppression theo chữ ký thông điệp**.
  - Khoá = (tên logger, level, chữ ký của thông điệp).
  - Lần đầu tiên gặp một khoá → log bình thường, ghi nhớ thời điểm.
  - Trong `SUPPRESS_WINDOW_S` giây sau đó → **bỏ qua** log, chỉ đếm số lần bị
    chặn.
  - Khi hết cửa sổ → log lại kèm số lần đã bị chặn ("... (bị chặn N lần)").

Nhờ vậy log vẫn **phản ánh đúng** tình trạng (nhìn thấy lỗi vẫn đang xảy ra
và nó xảy ra bao nhiêu lần) nhưng dung lượng bounded.

Bộ lọc này cài ở mức **root logger**, nên áp dụng cho mọi logger con —
không cần sửa từng lệnh `LOG.warning(...)` trong codebase.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, Tuple

# Cửa sổ suppression (giây).
SUPPRESS_WINDOW_S = 60.0

# Ngưỡng bỏ qua hoàn toàn — nếu một lỗi bị chặn quá nhiều lần trong 1 cửa sổ,
# chỉ báo cáo con số tổng (không log từng lần).
MAX_REPEAT_REPORTS = 1

# Ngưỡng: tin nhắn dài hơn số ký tự này sẽ bị cắt khi tạo chữ ký.
_SIGNATURE_MAX_LEN = 200

Key = Tuple[str, int, str]


class RateLimitFilter(logging.Filter):
    """Lọc log lặp lại — giữ lại nhịp log chậm, chặn phần spam."""

    def __init__(self, window_s: float = SUPPRESS_WINDOW_S) -> None:
        super().__init__()
        self.window_s = window_s
        self._lock = threading.Lock()
        # khoá -> (thời điểm log gần nhất, số lần bị chặn, số lần đã báo cáo)
        self._state: Dict[Key, Tuple[float, int, int]] = {}

    # ------------------------------------------------------------------ #
    @staticmethod
    def _signature(record: logging.LogRecord) -> str:
        """Chữ ký của thông điệp — bỏ qua các tham số thay đổi theo thời gian.

        Ví dụ: "Lỗi đọc PZEM: %s" với tham số là số thứ tự lần lặp sẽ tạo
        ra mỗi lần một chữ ký khác nhau → không bị chặn. Ta chỉ dùng *mẫu*
        thông điệp (`record.msg`) chứ không dùng thông điệp đã format, nên
        các thông điệp có tham số động vẫn được gom lại đúng.
        """
        try:
            msg = record.msg
            if not isinstance(msg, str):
                msg = str(msg)
        except Exception:  # noqa: BLE001
            msg = ""
        if len(msg) > _SIGNATURE_MAX_LEN:
            msg = msg[:_SIGNATURE_MAX_LEN] + "…"
        return msg

    # ------------------------------------------------------------------ #
    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        """Trả `True` để cho log đi qua, `False` để chặn."""
        key: Key = (record.name, record.levelno, self._signature(record))
        now = time.monotonic()

        with self._lock:
            last, suppressed, reports = self._state.get(key, (0.0, 0, 0))

            if now - last >= self.window_s:
                # Cửa sổ mới: cho log đi qua, kèm báo cáo số lần đã bị chặn.
                if suppressed and reports < MAX_REPEAT_REPORTS:
                    record.msg = f"{record.msg} (bị chặn {suppressed} lần trước đó)"
                    record.args = ()
                self._state[key] = (now, 0, reports + (1 if suppressed else 0))
                return True

            # Trong cửa sổ → chặn, chỉ đếm.
            self._state[key] = (last, suppressed + 1, reports)
            return False

    # ------------------------------------------------------------------ #
    def reset(self) -> None:
        """Xoá toàn bộ trạng thái (dùng khi test)."""
        with self._lock:
            self._state.clear()

    def stats(self) -> Dict[str, Any]:
        """Thống kê trạng thái chặn (để chẩn đoán)."""
        with self._lock:
            return {
                "keys": len(self._state),
                "suppressed_total": sum(v[1] for v in self._state.values()),
                "window_s": self.window_s,
            }


def install_rate_limit_filter(
    logger: logging.Logger,
    window_s: float = SUPPRESS_WINDOW_S,
) -> RateLimitFilter:
    """Cài bộ lọc lên logger cho trước (root logger)."""
    flt = RateLimitFilter(window_s=window_s)
    logger.addFilter(flt)
    return flt
