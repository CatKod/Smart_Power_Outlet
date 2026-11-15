"""Cấu hình và đường dẫn dữ liệu của PC Agent.

Cấu hình được lưu ở `%ProgramData%\\SmartPowerOutlet\\config.json` trên Windows
(dùng chung cho mọi user, sống sót qua cài đặt lại) và
`$XDG_CONFIG_HOME` hoặc `~/.config/smartpoweroutlet/` trên Linux.

Quy ước: **không bao giờ** ghi đè cấu hình đã lưu khi việc xác minh thất bại —
xem `discovery.py` (chính sách chống flapping).
"""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

LOG = logging.getLogger("pc_agent.config")

SCHEMA_VERSION = 1
APP_NAME = "SmartPowerOutlet"

# Ngưỡng cảnh báo mặc định cho một cổng ổ cắm đơn lẻ (W).
# PZEM-004T V3.0 cho phép tối đa 25000 W qua thanh ghi 0x0001.
DEFAULT_POWER_THRESHOLD_W = 25000


# --------------------------------------------------------------------------- #
# Đường dẫn theo nền tảng
# --------------------------------------------------------------------------- #
def _is_windows() -> bool:
    return sys.platform.startswith("win")


def config_dir() -> Path:
    """Thư mục cấu hình (read-write cho service)."""
    override = os.environ.get("SMARTPOWER_CONFIG_DIR")
    if override:
        return Path(override)

    if _is_windows():
        base = os.environ.get("ProgramData") or r"C:\ProgramData"
        return Path(base) / APP_NAME

    # Linux: tuân theo XDG nếu có, không thì ~/.config
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / APP_NAME.lower()
    return Path.home() / ".config" / APP_NAME.lower()


def data_dir() -> Path:
    """Thư mục dữ liệu (database, cache)."""
    override = os.environ.get("SMARTPOWER_DATA_DIR")
    if override:
        return Path(override)

    if _is_windows():
        base = os.environ.get("ProgramData") or r"C:\ProgramData"
        return Path(base) / APP_NAME / "data"

    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / APP_NAME.lower()
    return Path.home() / ".local" / "share" / APP_NAME.lower()


def log_dir() -> Path:
    """Thư mục log."""
    override = os.environ.get("SMARTPOWER_LOG_DIR")
    if override:
        return Path(override)
    return config_dir() / "logs"


def config_path() -> Path:
    return config_dir() / "config.json"


def database_path() -> Path:
    return data_dir() / "telemetry.db"


# --------------------------------------------------------------------------- #
# Schema
# --------------------------------------------------------------------------- #
@dataclass
class AgentConfig:
    """Cấu hình vận hành của PC Agent.

    `port` / `location` / `slave_address` là những giá trị được *dò ra* rồi
    lưu lại; các giá trị còn lại do người dùng (hoặc bản cài đặt) đặt.
    """

    schema_version: int = SCHEMA_VERSION

    # --- Định danh hiện trường (rack/meter) ---
    site_id: str = "site-01"
    rack_id: str = "rack-01"
    meter_id: str = "pdu-01"

    # --- Kết nối serial ---
    port: Optional[str] = None           # ví dụ "COM10"
    usb_location: Optional[str] = None    # ví dụ "1-4:x.3" — ổn định hơn COM number
    slave_address: int = 0x01
    baudrate: int = 9600
    poll_interval_s: float = 1.0

    # --- Ngưỡng cảnh báo ---
    power_threshold_w: int = DEFAULT_POWER_THRESHOLD_W
    voltage_min_v: float = 180.0
    voltage_max_v: float = 260.0
    offline_after_s: float = 30.0

    # --- API ---
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    api_token: Optional[str] = None       # None = chưa bật xác thực (chỉ chấp nhận local)

    # --- MQTT (giai đoạn sau, để trống = tắt) ---
    mqtt_host: Optional[str] = None
    mqtt_port: int = 1883
    mqtt_username: Optional[str] = None
    mqtt_password: Optional[str] = None

    # --- Lưu trữ ---
    raw_retention_days: int = 14
    hourly_retention_days: int = 365

    # --- Siêu dữ liệu ---
    last_verified_utc: Optional[str] = None
    extra: dict = field(default_factory=dict)

    # ------------------------------------------------------------------ #
    @property
    def topic_prefix(self) -> str:
        return f"smartoutlet/rack/{self.rack_id}/meter/{self.meter_id}"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AgentConfig":
        known = {f for f in cls.__dataclass_fields__ if f != "extra"}
        extra = dict(data.get("extra") or {})
        extra.update({k: v for k, v in data.items() if k not in known})
        kwargs = {k: v for k, v in data.items() if k in known}
        kwargs["extra"] = extra
        cfg = cls(**kwargs)
        cfg._migrate()
        return cfg

    def _migrate(self) -> None:
        """Nâng cấp schema cũ lên schema hiện tại."""
        if self.schema_version < SCHEMA_VERSION:
            LOG.info(
                "Nâng cấp cấu hình từ schema v%s lên v%s",
                self.schema_version, SCHEMA_VERSION,
            )
            self.schema_version = SCHEMA_VERSION


# --------------------------------------------------------------------------- #
# Ghi / đọc nguyên tử
# --------------------------------------------------------------------------- #
def atomic_write_json(path: Path, data: dict) -> None:
    """Ghi JSON theo kiểu nguyên tử (atomic).

    Quy trình: ghi file tạm **cùng thư mục** (bảo đảm cùng volume/FS) →
    `flush()` → `fsync()` → `os.replace()` (MoveFileExW/MOVEFILE_REPLACE_EXISTING
    trên NTFS, rename(2) atomic trên POSIX).

    Nếu mất điện giữa lúc ghi, file cũ vẫn nguyên vẹn — không bao giờ
    để lại file 0 byte hay JSON hỏng.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    tmp_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(path.parent),
            delete=False,
            prefix=f".{path.name}.tmp_",
        ) as tf:
            tmp_path = Path(tf.name)
            json.dump(data, tf, indent=2, ensure_ascii=False)
            tf.flush()
            os.fsync(tf.fileno())
        os.replace(tmp_path, path)
        tmp_path = None
    finally:
        if tmp_path is not None and tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


class ConfigStore:
    """Nạp/lưu `AgentConfig`."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path else config_path()

    def load(self) -> AgentConfig:
        if not self.path.exists():
            LOG.info("Không có file cấu hình %s — dùng cấu hình mặc định", self.path)
            return AgentConfig()
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return AgentConfig.from_dict(data)
        except Exception as exc:  # noqa: BLE001
            LOG.error(
                "Không đọc được cấu hình %s (%s) — dùng cấu hình mặc định. "
                "File sẽ KHÔNG bị ghi đè cho tới khi dò được thiết bị hợp lệ.",
                self.path, exc,
            )
            return AgentConfig()

    def save(self, cfg: AgentConfig) -> None:
        atomic_write_json(self.path, cfg.to_dict())
        LOG.info("Đã lưu cấu hình vào %s", self.path)


def load_config(path: Optional[Path] = None) -> AgentConfig:
    return ConfigStore(path).load()


def save_config(cfg: AgentConfig, path: Optional[Path] = None) -> None:
    ConfigStore(path).save(cfg)
