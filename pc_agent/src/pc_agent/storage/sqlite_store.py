"""Lưu trữ lịch sử đo vào SQLite (chế độ WAL).

Bảng `telemetry_raw` giữ mẫu thô theo chu kỳ lấy mẫu (mặc định 1 Hz) với
thời hạn ngắn; bảng `telemetry_hourly` tổng hợp theo giờ với thời hạn dài.
SQLite được chọn vì:
  - nằm gọn trong một file, không cần dịch vụ ngoài (đúng yêu cầu "service
    chạy độc lập 24/7");
  - chế độ WAL cho phép đọc đồng thời trong lúc ghi;
  - là thư viện chuẩn của Python — không thêm phụ thuộc nào.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

LOG = logging.getLogger("pc_agent.storage")

SCHEMA = """
CREATE TABLE IF NOT EXISTS telemetry_raw (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp     REAL    NOT NULL,
    timestamp_iso TEXT    NOT NULL,
    meter_id      TEXT    NOT NULL,
    slave_address INTEGER NOT NULL,
    voltage_v     REAL    NOT NULL,
    current_a     REAL    NOT NULL,
    power_w       REAL    NOT NULL,
    energy_wh     REAL    NOT NULL,
    frequency_hz  REAL    NOT NULL,
    power_factor  REAL    NOT NULL,
    alarm_state   INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_raw_meter_time
    ON telemetry_raw (meter_id, timestamp DESC);

CREATE TABLE IF NOT EXISTS telemetry_hourly (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    bucket_start      REAL    NOT NULL,
    meter_id          TEXT    NOT NULL,
    samples_count     INTEGER NOT NULL,
    energy_start_wh   REAL    NOT NULL,
    energy_end_wh     REAL    NOT NULL,
    energy_delta_wh   REAL    NOT NULL,
    power_min_w       REAL    NOT NULL,
    power_max_w       REAL    NOT NULL,
    power_avg_w       REAL    NOT NULL,
    voltage_min_v     REAL    NOT NULL,
    voltage_max_v     REAL    NOT NULL,
    voltage_avg_v     REAL    NOT NULL,
    current_max_a     REAL    NOT NULL,
    current_avg_a     REAL    NOT NULL,
    power_factor_avg  REAL    NOT NULL,
    load_factor       REAL    NOT NULL,
    alarm_trips_count INTEGER NOT NULL,
    UNIQUE (meter_id, bucket_start)
);
CREATE INDEX IF NOT EXISTS idx_hourly_meter_time
    ON telemetry_hourly (meter_id, bucket_start DESC);

CREATE TABLE IF NOT EXISTS events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       REAL NOT NULL,
    timestamp_iso   TEXT NOT NULL,
    meter_id        TEXT NOT NULL,
    event_type      TEXT NOT NULL,
    severity        TEXT NOT NULL DEFAULT 'warning',
    threshold_value REAL,
    observed_value  REAL,
    resolved_at     REAL,
    message         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_time
    ON events (timestamp DESC);
"""


class TelemetryStore:
    """Kho lưu trữ telemetry, an toàn khi dùng từ nhiều thread."""

    def __init__(self, db_path: Path, meter_id: str = "pdu-01") -> None:
        self.db_path = Path(db_path)
        self.meter_id = meter_id
        self._lock = threading.Lock()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    # ------------------------------------------------------------------ #
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        return conn

    def _init_schema(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(SCHEMA)
        LOG.info("Đã khởi tạo cơ sở dữ liệu %s", self.db_path)

    # ------------------------------------------------------------------ #
    def insert_sample(self, sample: Dict[str, Any]) -> None:
        """Ghi một mẫu thô."""
        ts = sample["timestamp"]
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO telemetry_raw (
                    timestamp, timestamp_iso, meter_id, slave_address,
                    voltage_v, current_a, power_w, energy_wh,
                    frequency_hz, power_factor, alarm_state
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ts,
                    sample.get("timestamp_iso")
                    or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)),
                    sample.get("meter_id") or self.meter_id,
                    sample.get("slave_address") or 0,
                    sample.get("voltage_v") or 0.0,
                    sample.get("current_a") or 0.0,
                    sample.get("power_w") or 0.0,
                    sample.get("energy_wh") or 0.0,
                    sample.get("frequency_hz") or 0.0,
                    sample.get("power_factor") or 0.0,
                    1 if sample.get("alarm_active") else 0,
                ),
            )

    # ------------------------------------------------------------------ #
    def rollup_hourly(self) -> None:
        """Tổng hợp giờ đã hoàn tất gần nhất vào bảng hourly."""
        now = time.time()
        current_hour = (int(now) // 3600) * 3600
        previous_hour = current_hour - 3600

        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO telemetry_hourly (
                    bucket_start, meter_id, samples_count,
                    energy_start_wh, energy_end_wh, energy_delta_wh,
                    power_min_w, power_max_w, power_avg_w,
                    voltage_min_v, voltage_max_v, voltage_avg_v,
                    current_max_a, current_avg_a, power_factor_avg,
                    load_factor, alarm_trips_count
                )
                SELECT
                    ? AS bucket_start,
                    meter_id,
                    COUNT(*),
                    MIN(energy_wh),
                    MAX(energy_wh),
                    MAX(energy_wh) - MIN(energy_wh),
                    MIN(power_w),
                    MAX(power_w),
                    AVG(power_w),
                    MIN(voltage_v),
                    MAX(voltage_v),
                    AVG(voltage_v),
                    MAX(current_a),
                    AVG(current_a),
                    AVG(power_factor),
                    CASE WHEN MAX(power_w) > 0
                         THEN AVG(power_w) / MAX(power_w) ELSE 0.0 END,
                    SUM(alarm_state)
                FROM telemetry_raw
                WHERE timestamp >= ? AND timestamp < ?
                GROUP BY meter_id
                """,
                (previous_hour, previous_hour, current_hour),
            )

    def purge_expired(self, raw_days: int = 14, hourly_days: int = 365) -> None:
        """Xoá dữ liệu cũ vượt thời hạn."""
        now = time.time()
        with self._lock, self._connect() as conn:
            conn.execute(
                "DELETE FROM telemetry_raw WHERE timestamp < ?", (now - raw_days * 86400,)
            )
            conn.execute(
                "DELETE FROM telemetry_hourly WHERE bucket_start < ?",
                (now - hourly_days * 86400),
            )
            conn.execute("PRAGMA wal_checkpoint(PASSIVE);")

    # ------------------------------------------------------------------ #
    def log_event(
        self,
        event_type: str,
        message: str,
        severity: str = "warning",
        threshold_value: Optional[float] = None,
        observed_value: Optional[float] = None,
        meter_id: Optional[str] = None,
    ) -> None:
        """Ghi một sự kiện (cảnh báo / lỗi)."""
        ts = time.time()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO events (
                    timestamp, timestamp_iso, meter_id, event_type,
                    severity, threshold_value, observed_value, message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ts,
                    time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)),
                    meter_id or self.meter_id,
                    event_type,
                    severity,
                    threshold_value,
                    observed_value,
                    message,
                ),
            )
        LOG.warning("[%s] %s — %s", severity.upper(), event_type, message)

    def resolve_event(self, event_type: str, meter_id: Optional[str] = None) -> None:
        """Đánh dấu sự kiện đang mở là đã xử lý."""
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE events SET resolved_at = ?
                WHERE resolved_at IS NULL AND event_type = ? AND meter_id = ?
                """,
                (time.time(), event_type, meter_id or self.meter_id),
            )

    # ------------------------------------------------------------------ #
    def query_history(
        self,
        meter_id: Optional[str] = None,
        since: Optional[float] = None,
        until: Optional[float] = None,
        resolution: str = "raw",
        limit: int = 5000,
    ) -> List[Dict[str, Any]]:
        """Truy vấn lịch sử. `resolution` = "raw" | "hourly"."""
        if resolution == "hourly":
            sql = """
                SELECT bucket_start AS timestamp, meter_id, samples_count,
                       energy_delta_wh, power_min_w, power_max_w, power_avg_w,
                       voltage_min_v, voltage_max_v, voltage_avg_v,
                       current_max_a, current_avg_a, power_factor_avg,
                       load_factor, alarm_trips_count
                FROM telemetry_hourly
                WHERE meter_id = ? AND bucket_start >= ? AND bucket_start <= ?
                ORDER BY bucket_start ASC LIMIT ?
            """
            lo = since if since is not None else 0.0
            hi = until if until is not None else time.time()
        else:
            sql = """
                SELECT timestamp, timestamp_iso, meter_id, slave_address,
                       voltage_v, current_a, power_w, energy_wh,
                       frequency_hz, power_factor, alarm_state
                FROM telemetry_raw
                WHERE meter_id = ? AND timestamp >= ? AND timestamp <= ?
                ORDER BY timestamp DESC LIMIT ?
            """
            lo = since if since is not None else 0.0
            hi = until if until is not None else time.time()

        with self._lock, self._connect() as conn:
            rows = conn.execute(
                sql, (meter_id or self.meter_id, lo, hi, limit)
            ).fetchall()
        return [dict(r) for r in rows]

    def query_events(self, active_only: bool = False, limit: int = 100) -> List[Dict[str, Any]]:
        """Truy vấn sự kiện."""
        sql = "SELECT * FROM events"
        params: List[Any] = []
        if active_only:
            sql += " WHERE resolved_at IS NULL"
        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        with self._lock, self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def stats(self, meter_id: Optional[str] = None) -> Dict[str, Any]:
        """Thống kê nhanh (dùng cho API /health)."""
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS samples, MIN(timestamp) AS first_ts, MAX(timestamp) AS last_ts
                FROM telemetry_raw WHERE meter_id = ?
                """,
                (meter_id or self.meter_id,),
            ).fetchone()
            events = conn.execute(
                "SELECT COUNT(*) FROM events WHERE resolved_at IS NULL AND meter_id = ?",
                (meter_id or self.meter_id,),
            ).fetchone()
        return {
            "samples": row["samples"] or 0,
            "first_timestamp": row["first_ts"],
            "last_timestamp": row["last_ts"],
            "open_events": events[0] or 0,
            "db_path": str(self.db_path),
        }
