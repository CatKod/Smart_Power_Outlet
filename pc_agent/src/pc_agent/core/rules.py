"""Bộ đánh giá ngưỡng cảnh báo — chạy trong tiến trình.

Vì sao đánh giá **trong tiến trình** chứ không đẩy lên broker hay rule engine?
  - độ trễ < 1 ms, không phụ thuộc mạng;
  - cảnh báo vẫn kêu được khi broker MQTT chết hoặc router mất mạng —
    đúng tình huống của một máy chủ rack;
  - đơn giản hơn, ít điểm hỏng hơn.

Cảnh báo được ghi vào SQLite và đánh dấu "đã xử lý" khi trở lại bình thường,
nên API có thể trả về danh sách sự kiện đang mở.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

LOG = logging.getLogger("pc_agent.rules")

EVENT_OVER_POWER = "OVER_POWER"
EVENT_OVER_CURRENT = "OVER_CURRENT"
EVENT_OVER_VOLTAGE = "OVER_VOLTAGE"
EVENT_UNDER_VOLTAGE = "UNDER_VOLTAGE"
EVENT_DEVICE_OFFLINE = "DEVICE_OFFLINE"
EVENT_DEVICE_ALARM = "DEVICE_ALARM"


class RuleEngine:
    """Đánh giá một mẫu đo theo ngưỡng cấu hình.

    `RuleEngine` **không** giữ trạng thái cảnh báo riêng — nó dựa vào
    `TelemetryStore.log_event` / `resolve_event` để không sinh log trùng.
    """

    def __init__(self, config, store, notifier=None) -> None:
        self.config = config
        self.store = store
        # Bộ gửi thông báo (A-7-7). `None` = không gửi (mặc định).
        self.notifier = notifier

    # ------------------------------------------------------------------ #
    def evaluate(self, sample: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Kiểm tra một mẫu. Trả về danh sách cảnh báo vừa kích hoạt."""
        fired: List[Dict[str, Any]] = []

        power = sample.get("power_w") or 0.0
        voltage = sample.get("voltage_v") or 0.0
        current = sample.get("current_a") or 0.0

        # --- Quá công suất ---
        if self.config.power_threshold_w and power > self.config.power_threshold_w:
            self.store.log_event(
                EVENT_OVER_POWER,
                f"Công suất {power:.1f} W vượt ngưỡng {self.config.power_threshold_w} W",
                severity="critical",
                threshold_value=float(self.config.power_threshold_w),
                observed_value=power,
            )
            fired.append({
                "type": EVENT_OVER_POWER,
                "observed": power,
                "threshold": float(self.config.power_threshold_w),
            })
            self._notify(
                EVENT_OVER_POWER,
                "Quá tải công suất",
                f"Công suất {power:.1f} W vượt ngưỡng "
                f"{self.config.power_threshold_w} W.",
            )
        else:
            self.store.resolve_event(EVENT_OVER_POWER)

        # --- Quá dòng (A-7-6) ---
        # Ngưỡng dòng điện bắt được trường hợp quá tải mà công suất chưa vượt
        # ngưỡng — ví dụ tải có PF thấp (động cơ, chấn lưu) rút dòng lớn nhưng
        # công suất thực chưa tới trần công suất ổ cắm.
        current_threshold = getattr(self.config, "current_threshold_a", None)
        if current_threshold and current > current_threshold:
            self.store.log_event(
                EVENT_OVER_CURRENT,
                f"Dòng điện {current:.2f} A vượt ngưỡng {current_threshold} A",
                severity="critical",
                threshold_value=float(current_threshold),
                observed_value=current,
            )
            fired.append({
                "type": EVENT_OVER_CURRENT,
                "observed": current,
                "threshold": float(current_threshold),
            })
            self._notify(
                EVENT_OVER_CURRENT,
                "Quá dòng",
                f"Dòng điện {current:.2f} A vượt ngưỡng {current_threshold} A.",
            )
        else:
            self.store.resolve_event(EVENT_OVER_CURRENT)

        # --- Quá điện áp ---
        if self.config.voltage_max_v and voltage > self.config.voltage_max_v:
            self.store.log_event(
                EVENT_OVER_VOLTAGE,
                f"Điện áp {voltage:.1f} V vượt ngưỡng {self.config.voltage_max_v} V",
                severity="critical",
                threshold_value=float(self.config.voltage_max_v),
                observed_value=voltage,
            )
            fired.append({
                "type": EVENT_OVER_VOLTAGE,
                "observed": voltage,
                "threshold": float(self.config.voltage_max_v),
            })
            self._notify(
                EVENT_OVER_VOLTAGE,
                "Quá điện áp",
                f"Điện áp {voltage:.1f} V vượt ngưỡng "
                f"{self.config.voltage_max_v} V.",
            )
        else:
            self.store.resolve_event(EVENT_OVER_VOLTAGE)

        # --- Sụt áp ---
        if self.config.voltage_min_v and voltage < self.config.voltage_min_v:
            self.store.log_event(
                EVENT_UNDER_VOLTAGE,
                f"Điện áp {voltage:.1f} V thấp hơn ngưỡng {self.config.voltage_min_v} V",
                severity="warning",
                threshold_value=float(self.config.voltage_min_v),
                observed_value=voltage,
            )
            fired.append({
                "type": EVENT_UNDER_VOLTAGE,
                "observed": voltage,
                "threshold": float(self.config.voltage_min_v),
            })
        else:
            self.store.resolve_event(EVENT_UNDER_VOLTAGE)

        # --- Cảnh báo tích hợp của PZEM (ngưỡng quá tải phần cứng) ---
        if sample.get("alarm_active"):
            self.store.log_event(
                EVENT_DEVICE_ALARM,
                "PZEM báo động quá tải (thanh ghi cảnh báo 0x0009 = 0xFFFF)",
                severity="critical",
                observed_value=1.0,
            )
            fired.append({"type": EVENT_DEVICE_ALARM, "observed": 1.0, "threshold": 0.0})
            self._notify(
                EVENT_DEVICE_ALARM,
                "PZEM báo động quá tải",
                "PZEM báo động quá tải (thanh ghi cảnh báo 0x0009 = 0xFFFF).",
            )
        else:
            self.store.resolve_event(EVENT_DEVICE_ALARM)

        return fired

    # ------------------------------------------------------------------ #
    def mark_offline(self, reason: str) -> None:
        """Ghi nhận thiết bị mất kết nối."""
        self.store.log_event(
            EVENT_DEVICE_OFFLINE, reason, severity="critical"
        )
        self._notify(EVENT_DEVICE_OFFLINE, "Thiết bị offline", reason)

    def clear_offline(self) -> None:
        self.store.resolve_event(EVENT_DEVICE_OFFLINE)

    # ------------------------------------------------------------------ #
    def _notify(self, event_type: str, title: str, message: str) -> None:
        """Gửi thông báo tổng hợp cho sự kiện mức `critical` (A-7-7).

        `notify()` của dispatcher **không** bao giờ raise hay block — nhưng ta
        vẫn bọc trong try/except để một lỗi lạ (ví dụ dispatcher bị thay thế
        bởi object khác trong test) không làm hỏng vòng lấy mẫu.
        """
        if self.notifier is None:
            return
        try:
            self.notifier.notify(title, f"[{event_type}] {message}", severity="critical")
        except Exception as exc:  # noqa: BLE001
            LOG.warning("Không gửi được thông báo cho %s: %s", event_type, exc)
