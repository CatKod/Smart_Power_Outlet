"""Vòng lấy mẫu Modbus-RTU — trái tim của PC Agent.

Đây là thread chạy suốt đời của service. Nó giữ **một** phiên serial duy nhất
(Windows không cho hai tiến trình mở cùng một cổng COM) và:

    1. Dò tìm thiết bị nếu chưa có phiên (dùng `discovery.PortDiscovery`).
    2. Đọc mẫu theo chu kỳ cấu hình.
    3. Đẩy mẫu vào `StateStore`, `TelemetryStore` và `RuleEngine`.
    4. Tự phục hồi khi thiết bị bị rút, cổng bị chiếm, hoặc lỗi đọc.

Về vòng đời: service dừng → `stop_event` được set → thread thoát sau khi
đóng cổng serial. Không dùng `daemon=True` một cách mù quáng; việc dọn dẹp
được làm tường minh trong `finally`.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from typing import Any, Dict, Optional

from ..config import AgentConfig, ConfigStore
from ..discovery import PortDiscovery, ProbeResult
from ..drivers.pzem004t import Pzem004T, PzemError
from .rules import RuleEngine
from .state import StateStore

LOG = logging.getLogger("pc_agent.poller")

# Backoff khi không tìm thấy thiết bị (giây)
RETRY_OFFLINE_S = 5.0
RETRY_ERROR_S = 3.0


class ModbusPoller(threading.Thread):
    """Thread lấy mẫu từ PZEM-004T."""

    def __init__(
        self,
        config: AgentConfig,
        state: StateStore,
        store,
        rules: Optional[RuleEngine] = None,
        config_store: Optional[ConfigStore] = None,
        simulate: bool = False,
    ) -> None:
        super().__init__(name="ModbusPoller", daemon=True)
        self.config = config
        self.state = state
        self.store = store
        self.rules = rules or RuleEngine(config, store)
        self.config_store = config_store or ConfigStore()
        self.discovery = PortDiscovery(config, self.config_store)
        self.simulate = simulate

        self._stop_event = threading.Event()
        self._session: Optional[Pzem004T] = None
        self._session_lock = threading.Lock()
        self._last_rollup = 0.0
        self._last_purge = 0.0
        self._sim_tick = 0
        # Watchdog (A-9-1): thời điểm nhận mẫu thành công gần nhất.
        self._last_sample_at: Optional[float] = None
        self._offline_logged = False

    # ------------------------------------------------------------------ #
    # Điều khiển
    # ------------------------------------------------------------------ #
    def stop(self, timeout: float = 5.0) -> None:
        """Yêu cầu dừng và chờ thread kết thúc."""
        LOG.info("Yêu cầu dừng vòng lấy mẫu...")
        self._stop_event.set()
        if self.is_alive():
            self.join(timeout=timeout)
        self._close_session()
        LOG.info("Vòng lấy mẫu đã dừng.")

    @property
    def stopping(self) -> bool:
        return self._stop_event.is_set()

    # ------------------------------------------------------------------ #
    # Phiên serial
    # ------------------------------------------------------------------ #
    def _open_session(self, port: str, address: int) -> Pzem004T:
        session = Pzem004T(
            port=port,
            baudrate=self.config.baudrate,
            address=address,
            timeout=1.0,
        )
        session.open()
        return session

    def _close_session(self) -> None:
        with self._session_lock:
            if self._session is not None:
                try:
                    self._session.close()
                except Exception:  # noqa: BLE001
                    pass
                self._session = None

    # ------------------------------------------------------------------ #
    # Vòng chính
    # ------------------------------------------------------------------ #
    def run(self) -> None:  # noqa: C901 - vòng chính có nhiều nhánh lỗi
        LOG.info(
            "Bắt đầu PC Agent — site=%s rack=%s meter=%s",
            self.config.site_id, self.config.rack_id, self.config.meter_id,
        )

        while not self.stopping:
            try:
                if not self._ensure_device():
                    self._stop_event.wait(RETRY_OFFLINE_S)
                    continue

                self._poll_loop()
            except Exception as exc:  # noqa: BLE001
                LOG.exception("Lỗi không mong đợi trong vòng lấy mẫu: %s", exc)
                self.state.set_error(f"Lỗi không mong đợi: {exc}")
                self._stop_event.wait(RETRY_ERROR_S)

        self._close_session()
        self.state.set_connected(False)

    # ------------------------------------------------------------------ #
    def _ensure_device(self) -> bool:
        """Đảm bảo có phiên serial hợp lệ. Trả False nếu chưa tìm thấy."""
        if self.simulate:
            # Chế độ mô phỏng: không cần phiên serial thật.
            if not self.state.snapshot()["status"]["connected"]:
                self.state.set_port("SIMULATED", self.config.slave_address)
                self.state.set_connected(True)
                self.rules.clear_offline()
                LOG.info(
                    "Chế độ mô phỏng — không đọc phần cứng thật, sinh dữ liệu giả."
                )
            return True

        with self._session_lock:
            if self._session is not None and self._session.is_open:
                return True

        result = self.discovery.discover()
        if result is None or not result.ok:
            self.state.set_connected(False)
            self._check_watchdog()
            if result is not None and result.status == "PORT_BUSY":
                self.state.set_error(result.detail)
                LOG.warning("Cổng đang bị chiếm: %s", result.detail)
            else:
                self.state.set_error(
                    "Chưa tìm thấy PZEM-004T trên bất kỳ cổng serial nào. "
                    "Kiểm tra: (1) USB-TTL đã cắm chưa, "
                    "(2) PZEM đã có nguồn lưới AC 220V ở chân L/N chưa."
                )
                LOG.warning("Chưa tìm thấy PZEM-004T — sẽ thử lại sau %.0fs", RETRY_OFFLINE_S)
            return False

        # Xác minh thành công → mới ghi nhớ (chính sách chống flapping)
        self.discovery.remember(result)
        self.config = self.discovery.config

        try:
            session = self._open_session(result.port, result.address or self.config.slave_address)
        except PzemError as exc:
            self.state.set_error(str(exc))
            LOG.error("Không mở được cổng %s: %s", result.port, exc)
            return False

        with self._session_lock:
            self._session = session

        self.state.set_port(result.port, result.address)
        self.state.set_connected(True)
        self.rules.clear_offline()
        LOG.info(
            "Đã kết nối PZEM-004T: cổng=%s, địa chỉ=0x%02X, %d baud",
            result.port, result.address or 0, self.config.baudrate,
        )
        return True

    # ------------------------------------------------------------------ #
    def _simulate_metrics(self):
        """Sinh mẫu đo giả cho chế độ mô phỏng (không cần phần cứng).

        Dùng để kiểm thử giao diện, API và luồng ghi DB khi chưa có thiết bị.
        Giá trị dao động quanh điểm danh nghĩa của lưới 220 V / 50 Hz.
        """
        from ..drivers.pzem004t import PzemMetrics

        self._sim_tick += 1
        t = self._sim_tick
        voltage = 220.0 + 2.0 * math.sin(t / 7.0)
        current = 0.75 + 0.15 * math.sin(t / 3.0)
        power_factor = 0.95
        power = voltage * current * power_factor
        energy_wh = 1000.0 + t * power / 3600.0

        return PzemMetrics(
            voltage=round(voltage, 1),
            current=round(current, 3),
            power=round(power, 1),
            energy=int(energy_wh),
            energy_kwh=round(energy_wh / 1000.0, 4),
            frequency=50.0,
            power_factor=power_factor,
            alarm=0x0000,
        )

    # ------------------------------------------------------------------ #
    def _poll_loop(self) -> None:
        """Vòng đọc liên tục cho tới khi có lỗi hoặc được yêu cầu dừng."""
        while not self.stopping:
            try:
                if self.simulate:
                    metrics = self._simulate_metrics()
                else:
                    with self._session_lock:
                        session = self._session
                    if session is None:
                        return
                    metrics = session.read()

                sample = self._to_sample(metrics)

                self.state.set_sample(sample)
                self.store.insert_sample(sample)
                self.rules.evaluate(sample)
                self._last_sample_at = time.time()
                self._offline_logged = False

                self._maybe_maintenance()

            except PzemError as exc:
                self._handle_pzem_error(str(exc))
                return
            except Exception as exc:  # noqa: BLE001
                self.state.set_error(f"Lỗi không mong đợi khi đọc: {exc}")
                LOG.exception("Lỗi không mong đợi khi đọc PZEM")
                self._close_session()
                self._stop_event.wait(RETRY_ERROR_S)
                return

            self._stop_event.wait(self.config.poll_interval_s)

    # ------------------------------------------------------------------ #
    def _check_watchdog(self) -> None:
        """Watchdog (A-9-1): ghi `DEVICE_OFFLINE` khi im lặng quá lâu.

        Ngưỡng lấy từ `config.offline_after_s` (mặc định 30 s). Ý nghĩa: nếu
        agent **không nhận được mẫu nào** trong khoảng thời gian đó, thì
        coi như thiết bị đã offline — kể cả khi `discovery` không báo lỗi
        rõ ràng (ví dụ cổng vẫn mở được nhưng thiết bị im lặng).

        Chỉ ghi **một lần** cho mỗi lần offline; khi có dữ liệu trở lại thì
        `rules.clear_offline()` đóng sự kiện và cờ `_offline_logged` reset.
        """
        if self._last_sample_at is None:
            return

        limit = float(getattr(self.config, "offline_after_s", 30.0) or 30.0)
        silent_for = time.time() - self._last_sample_at
        if silent_for < limit or self._offline_logged:
            return

        self._offline_logged = True
        reason = (
            f"Không nhận được dữ liệu trong {silent_for:.0f}s "
            f"(ngưỡng {limit:.0f}s) — coi như thiết bị offline."
        )
        LOG.error("Watchdog: %s", reason)
        self.rules.mark_offline(reason)

    # ------------------------------------------------------------------ #
    def _handle_pzem_error(self, message: str) -> None:
        """Phân loại lỗi đọc và quyết định thời gian chờ trước khi thử lại."""
        self.state.set_error(message)
        self._close_session()
        self._check_watchdog()

        busy = ("Access is denied" in message or "PermissionError" in message
                or "bị tiến trình khác chiếm" in message)
        missing = ("không tồn tại" in message or "FileNotFoundError" in message)

        if busy:
            LOG.error(
                "Cổng bị tiến trình khác chiếm. Đóng serial monitor / PuTTY / "
                "PlatformIO đang dùng cổng này. (KHÔNG phải lỗi nguồn hay dây.)"
            )
            self._stop_event.wait(30.0)
        elif missing:
            LOG.warning("Thiết bị đã bị rút khỏi cổng — sẽ quét lại khi cắm lại.")
            self._stop_event.wait(RETRY_OFFLINE_S)
        else:
            LOG.warning("Lỗi đọc PZEM: %s", message)
            self._stop_event.wait(RETRY_ERROR_S)

    # ------------------------------------------------------------------ #
    def _to_sample(self, metrics) -> Dict[str, Any]:
        """Chuyển `PzemMetrics` thành bản ghi telemetry."""
        return {
            "timestamp": metrics.timestamp,
            "timestamp_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(metrics.timestamp)),
            "meter_id": self.config.meter_id,
            "slave_address": self.config.slave_address,
            "voltage_v": metrics.voltage,
            "current_a": metrics.current,
            "power_w": metrics.power,
            "energy_wh": metrics.energy,
            "energy_kwh": metrics.energy_kwh,
            "frequency_hz": metrics.frequency,
            "power_factor": metrics.power_factor,
            "alarm_active": metrics.alarm == 0xFFFF,
        }

    # ------------------------------------------------------------------ #
    def _maybe_maintenance(self) -> None:
        """Tổng hợp theo giờ + dọn dữ liệu cũ (chạy thưa để không tốn CPU)."""
        now = time.time()
        if now - self._last_rollup >= 300:      # 5 phút
            self._last_rollup = now
            try:
                self.store.rollup_hourly()
            except Exception as exc:  # noqa: BLE001
                LOG.warning("Không tổng hợp theo giờ được: %s", exc)
        if now - self._last_purge >= 3600:      # 1 giờ
            self._last_purge = now
            try:
                self.store.purge_expired(
                    self.config.raw_retention_days,
                    self.config.hourly_retention_days,
                )
            except Exception as exc:  # noqa: BLE001
                LOG.warning("Không dọn dữ liệu cũ được: %s", exc)
