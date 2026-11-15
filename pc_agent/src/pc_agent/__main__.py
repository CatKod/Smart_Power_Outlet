"""Điểm khởi chạy của PC Agent.

Cùng một tệp này phục vụ **hai** chế độ:

  - **Foreground** (phát triển): `python -m pc_agent` — chạy tay, có log console,
    Ctrl+C dừng gọn gàng.
  - **Service** (sản xuất): được `pc_agent.deploy.windows_service` (pywin32)
    hoặc `systemd` gọi vào `run_agent()`.

Nguyên tắc: **không fork mã nguồn**. Cùng một `run_agent()` chạy dưới cả hai
chế độ — khác biệt chỉ nằm ở việc ai chịu trách nhiệm bắt tín hiệu dừng.

    python -m pc_agent --simulate          # chạy thử không cần phần cứng
    python -m pc_agent --port COM10         # ép cổng
    python -m pc_agent --host 0.0.0.0       # mở cho mạng LAN
    python -m pc_agent --exhaustive-scan    # quét toàn bộ dải địa chỉ
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Optional

from .api.server import AgentServer
from .config import AgentConfig, ConfigStore, database_path, log_dir
from .core.poller import ModbusPoller
from .core.rules import RuleEngine
from .core.state import StateStore
from .logging_setup import setup_logging
from .storage.sqlite_store import TelemetryStore

LOG = logging.getLogger("pc_agent")


# --------------------------------------------------------------------------- #
# Tín hiệu dừng
# --------------------------------------------------------------------------- #
def install_signal_handlers(stop_event: threading.Event) -> None:
    """Ánh xạ tín hiệu hệ điều hành → `stop_event`.

    - `SIGINT`  : Ctrl+C ở chế độ foreground.
    - `SIGTERM` : systemd `stop` / `kill` trên Linux.
    - `SIGBREAK`: Windows `CTRL_BREAK_EVENT` (service wrapper gửi tín hiệu này).
    """

    def handler(signum, _frame):
        try:
            name = signal.Signals(signum).name
        except (ValueError, AttributeError):
            name = str(signum)
        LOG.info("Nhận tín hiệu %s — đang dừng êm ái...", name)
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, handler)
        except (ValueError, OSError):
            pass
    if hasattr(signal, "SIGBREAK"):
        try:
            signal.signal(signal.SIGBREAK, handler)
        except (ValueError, OSError):
            pass


# --------------------------------------------------------------------------- #
# Vòng đời
# --------------------------------------------------------------------------- #
class AgentRuntime:
    """Giữ các thành phần của agent và điều phối start/stop."""

    def __init__(
        self,
        config: AgentConfig,
        config_store: Optional[ConfigStore] = None,
        simulate: bool = False,
    ) -> None:
        self.config = config
        self.config_store = config_store or ConfigStore()
        self.state = StateStore()
        self.store = TelemetryStore(database_path(), config.meter_id)
        self.rules = RuleEngine(config, self.store)
        self.poller: Optional[ModbusPoller] = None
        self.server: Optional[AgentServer] = None
        self.stop_event = threading.Event()
        self.simulate = simulate

    def start(self) -> None:
        self.server = AgentServer(self.config, self.state, self.store)
        self.server.start()

        self.poller = ModbusPoller(
            config=self.config,
            state=self.state,
            store=self.store,
            rules=self.rules,
            config_store=self.config_store,
            simulate=self.simulate,
        )
        self.poller.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.poller is not None:
            self.poller.stop()
        if self.server is not None:
            self.server.stop()
        self.state.set_connected(False)

    def wait(self) -> None:
        """Chờ cho tới khi có yêu cầu dừng."""
        while not self.stop_event.wait(0.5):
            pass


def run_agent(
    config: Optional[AgentConfig] = None,
    config_store: Optional[ConfigStore] = None,
    simulate: bool = False,
    console: bool = True,
) -> int:
    """Chạy agent tới khi bị dừng. Trả về mã thoát."""
    setup_logging(log_dir(), console=console)

    store = config_store or ConfigStore()
    cfg = config if config is not None else store.load()

    if simulate:
        LOG.warning("Chế độ mô phỏng — không đọc phần cứng thật.")
        cfg.port = cfg.port or "SIMULATED"
        cfg.slave_address = 0x01

    runtime = AgentRuntime(cfg, store, simulate=simulate)
    install_signal_handlers(runtime.stop_event)

    LOG.info(
        "PC Agent khởi động | site=%s rack=%s meter=%s | cổng=%s | API=%s:%d",
        cfg.site_id, cfg.rack_id, cfg.meter_id, cfg.port, cfg.api_host, cfg.api_port,
    )

    try:
        runtime.start()
        runtime.wait()
    except Exception:
        LOG.exception("Lỗi nghiêm trọng trong PC Agent")
        return 1
    finally:
        runtime.stop()
        LOG.info("PC Agent đã dừng.")

    return 0


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="pc_agent",
        description="Electronic PC Agent — giám sát năng lượng PZEM-004T (Modbus-RTU)",
    )
    # Lưu ý: tránh ký tự '%' trong help string — argparse dùng %-formatting.
    p.add_argument("--config", help="Đường dẫn file cấu hình (mặc định thư mục ProgramData)")
    p.add_argument("--port", help="Ép cổng serial, bỏ qua việc tự dò")
    p.add_argument("--address", type=lambda s: int(s, 0), help="Ép địa chỉ Modbus slave")
    p.add_argument("--host", help="Địa chỉ lắng nghe API")
    p.add_argument("--api-port", type=int, help="Cổng API")
    p.add_argument("--interval", type=float, help="Chu kỳ lấy mẫu (giây)")
    p.add_argument("--meter-id", help="Định danh meter")
    p.add_argument("--rack-id", help="Định danh rack")
    p.add_argument(
        "--exhaustive-scan",
        action="store_true",
        help="Quét toàn bộ dải địa chỉ slave 0x01..0xF7 (chậm, ~37s/cổng)",
    )
    p.add_argument(
        "--simulate",
        action="store_true",
        help="Chạy thử không cần phần cứng",
    )
    p.add_argument(
        "--no-console-log",
        action="store_true",
        help="Không ghi log ra console (dùng khi chạy dưới service)",
    )
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)

    store = ConfigStore(Path(args.config)) if args.config else ConfigStore()
    cfg = store.load()

    if args.port:
        cfg.port = args.port
    if args.address is not None:
        cfg.slave_address = args.address
    if args.host:
        cfg.api_host = args.host
    if args.api_port:
        cfg.api_port = args.api_port
    if args.interval:
        cfg.poll_interval_s = args.interval
    if args.meter_id:
        cfg.meter_id = args.meter_id
    if args.rack_id:
        cfg.rack_id = args.rack_id

    if args.exhaustive_scan:
        from .discovery import discover_device
        from .logging_setup import setup_logging as _setup
        _setup(log_dir(), console=not args.no_console_log)
        result, cfg = discover_device(cfg, store, exhaustive=True)
        if result and result.ok:
            LOG.info(
                "Tìm thấy PZEM-004T: cổng=%s, địa chỉ=0x%02X, USB path=%s",
                result.port, result.address, result.location,
            )
            print(f"FOUND port={result.port} address=0x{result.address:02X} location={result.location}")
            return 0
        LOG.error("Không tìm thấy PZEM-004T.")
        print("NOT FOUND")
        return 2

    return run_agent(
        config=cfg,
        config_store=store,
        simulate=args.simulate,
        console=not args.no_console_log,
    )


if __name__ == "__main__":
    raise SystemExit(main())
