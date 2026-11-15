#!/usr/bin/env python3
"""Soak test dài hạn cho PC Agent — đo kích thước DB/WAL và rò rỉ bộ nhớ.

Mục tiêu (task A-6-6)
----------------------
Agent chạy 24/7. Câu hỏi cần trả lời bằng số liệu:

  1. **DB có phình vô hạn không?**  → đo kích thước `telemetry.db`, `-wal`,
     `-shm` theo thời gian, so với ngân sách đề ra.
  2. **WAL có bị kẹt không?**  → WAL chỉ được checkpoint khi đủ ngưỡng; nếu
     agent mở kết nối mới mỗi lần ghi (như `insert_sample` hiện tại) thì WAL
     phải được truncate — nếu không, `-wal` phình theo thời gian.
  3. **RAM có rò rỉ không?**  → đo RSS của tiến trình sau mỗi chu kỳ.
  4. **Retention có hoạt động không?**  → số dòng `telemetry_raw` phải bị
     giới hạn theo `raw_retention_days`, không tăng vô hạn.

Cách chạy
----------
Soak ngắn (kiểm tra nhanh, ~2 phút)::

    python pc_agent/tools/soak_test.py --duration 120 --interval 10

Soak 24 giờ thật (để chạy qua đêm)::

    python pc_agent/tools/soak_test.py --duration 86400 --interval 300

Soak với tốc độ ghi tăng tốc (nhồi dữ liệu để phát hiện rò nhanh)::

    python pc_agent/tools/soak_test.py --duration 300 --rate 20

Kết quả được ghi ra:
  - ``soak_report.json`` — máy đọc được, để CI/script phân tích
  - ``soak_report.csv``  — mở bằng Excel
  - in ra console theo từng chu kỳ

Ngưỡng cảnh báo (mặc định, có thể chỉnh bằng CLI)
---------------------------------------------------
  ==========================  ==========
  Chỉ số                     Ngưỡng
  ==========================  ==========
  ``telemetry.db``            200 MB
  ``telemetry.db-wal``        64 MB
  Tổng DB + WAL + SHM         256 MB
  RSS bộ nhớ                 512 MB
  Tăng RSS sau 2/3 thời gian  20 %
  ==========================  ==========
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# Cho phép chạy trực tiếp từ thư mục tools/ mà chưa cài package.
_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from pc_agent.storage.sqlite_store import TelemetryStore  # noqa: E402


# --------------------------------------------------------------------------- #
# Ngưỡng
# --------------------------------------------------------------------------- #
@dataclass
class Thresholds:
    """Ngân sách tài nguyên — vượt ngưỡng này thì soak test báo FAIL."""

    db_max_mb: float = 200.0
    wal_max_mb: float = 64.0
    total_max_mb: float = 256.0
    rss_max_mb: float = 512.0
    rss_growth_pct: float = 20.0
    # Giới hạn "đúng" của số dòng raw: retention_days * mẫu/ngày * hệ số an toàn.
    # Với poll 1 Hz → 86 400 mẫu/ngày. Cho phép rộng 1.5× vì purge chạy theo chu kỳ.
    raw_rows_per_day: int = 86_400


# --------------------------------------------------------------------------- #
# Mẫu đo
# --------------------------------------------------------------------------- #
@dataclass
class Sample:
    """Một mốc đo trong quá trình soak."""

    elapsed_s: float
    timestamp_iso: str
    db_bytes: int = 0
    wal_bytes: int = 0
    shm_bytes: int = 0
    total_bytes: int = 0
    raw_rows: int = 0
    hourly_rows: int = 0
    event_rows: int = 0
    rss_bytes: int = 0
    heap_bytes: int = 0
    threads: int = 0
    write_ms: float = 0.0
    db_growth_mb: float = 0.0
    wal_growth_mb: float = 0.0


@dataclass
class Verdict:
    """Kết luận của soak test."""

    status: str = "UNKNOWN"          # PASS | WARN | FAIL
    checks: List[Dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    db_growth_mb_per_hour: float = 0.0
    rss_growth_pct: float = 0.0
    duration_s: float = 0.0


# --------------------------------------------------------------------------- #
# Tiện ích
# --------------------------------------------------------------------------- #
def _rss_bytes() -> int:
    """RSS của tiến trình hiện tại (bytes).

    Thứ tự ưu tiên:
      1. ``psutil`` (nếu cài) — chính xác nhất, cross-platform.
      2. ``/proc/self/statm`` — Linux.
      3. ``GetProcessMemoryInfo`` qua ctypes — Windows (không cần cài thêm).
    """
    try:
        import psutil  # type: ignore

        return int(psutil.Process().memory_info().rss)
    except Exception:
        pass

    # Linux
    try:
        with open("/proc/self/statm", "r", encoding="utf-8") as fh:
            pages = int(fh.read().split()[1])
        return pages * os.sysconf("SC_PAGE_SIZE")
    except Exception:
        pass

    # Windows — PROCESS_MEMORY_COUNTERS.WorkingSetSize
    #
    # LƯU Ý: phải khai báo `argtypes`/`restype` rõ ràng. Nếu gọi
    # `psapi.GetProcessMemoryInfo` mà không khai báo, con trỏ 64-bit bị cắt cụt
    # → hàm trả về 0 và WorkingSetSize luôn bằng 0 (rất dễ bị nhầm là
    # "bộ nhớ 0 MB"). Dùng `K32GetProcessMemoryInfo` (kernel32) là bản
    # được khuyến nghị từ Windows 7 trở lên.
    try:
        import ctypes
        from ctypes import wintypes

        class _PROCESS_MEMORY_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        getter = getattr(k32, "K32GetProcessMemoryInfo", None)
        if getter is None:
            getter = k32.GetProcessMemoryInfo
        getter.restype = ctypes.c_int
        getter.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(_PROCESS_MEMORY_COUNTERS),
            wintypes.DWORD,
        ]

        handle = k32.GetCurrentProcess()
        counters = _PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(counters)
        if getter(handle, ctypes.byref(counters), counters.cb):
            return int(counters.WorkingSetSize)
    except Exception:
        pass

    return 0


def _heap_bytes() -> int:
    """Bộ nhớ heap của Python (bytes) — 0 nếu không lấy được."""
    try:
        import gc  # noqa: F401  (buộc GC chạy trước khi đo)

        gc.collect()
        import tracemalloc

        return int(tracemalloc.get_traced_memory()[0])
    except Exception:
        return 0


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size if path.exists() else 0
    except OSError:
        return 0


def _thread_count() -> int:
    try:
        import threading

        return threading.active_count()
    except Exception:
        return 0


def _fmt_mb(n: int) -> str:
    return f"{n / (1024 * 1024):.2f} MB"


# --------------------------------------------------------------------------- #
# Bộ sinh mẫu giả lập
# --------------------------------------------------------------------------- #
class SampleGenerator:
    """Sinh mẫu đo giống hệt PZEM-004T thật.

    Mục tiêu là tạo **phân bố dữ liệu** giống thực tế (công suất biến động
    theo chu kỳ ngày, điện áp dao động quanh 220 V) để phát hiện rò rỉ bộ nhớ
    do tích luỹ object chứ không chỉ do số lượng row.
    """

    def __init__(self, seed: int = 20261115) -> None:
        self._rng = random.Random(seed)
        self._energy_wh = 12_345.6
        self._t0 = time.time()

    def next(self, meter_id: str = "pdu-01") -> Dict[str, Any]:
        now = time.time()
        # Chưa trôi qua 1 giây → lấy mẫu ngay trước đó.
        elapsed = max(now - self._t0, 0.001)
        phase = (elapsed % 86400.0) / 86400.0 * 2 * 3.14159265

        # Công suất: nền + sóng ngày + nhiễu.
        base_w = 900.0 + 600.0 * (0.5 + 0.5 * __import__("math").sin(phase - 1.57))
        noise = self._rng.gauss(0, 45.0)
        power_w = max(base_w + noise, 0.0)

        # Dòng điện = P / V (cos phi ≈ 0.95)
        voltage_v = 220.0 + self._rng.gauss(0, 2.2)
        voltage_v = min(max(voltage_v, 198.0), 242.0)
        pf = 0.95 + self._rng.gauss(0, 0.015)
        pf = min(max(pf, 0.70), 1.0)
        current_a = power_w / max(voltage_v * pf, 1.0)

        # Năng lượng tích luỹ tăng dần.
        self._energy_wh += power_w / 3600.0

        return {
            "timestamp": now,
            "timestamp_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
            "meter_id": meter_id,
            "slave_address": 1,
            "voltage_v": round(voltage_v, 2),
            "current_a": round(current_a, 4),
            "power_w": round(power_w, 2),
            "energy_wh": round(self._energy_wh, 3),
            "frequency_hz": round(50.0 + self._rng.gauss(0, 0.05), 2),
            "power_factor": round(pf, 3),
            "alarm_active": False,
        }


# --------------------------------------------------------------------------- #
# Soak test
# --------------------------------------------------------------------------- #
class SoakTest:
    def __init__(
        self,
        db_path: Path,
        duration_s: float,
        interval_s: float,
        rate: int,
        thresholds: Thresholds,
        meter_id: str = "pdu-01",
    ) -> None:
        self.db_path = Path(db_path)
        self.duration_s = duration_s
        self.interval_s = interval_s
        self.rate = max(rate, 1)
        self.thresholds = thresholds
        self.meter_id = meter_id

        self.store = TelemetryStore(self.db_path, meter_id=meter_id)
        self.generator = SampleGenerator()
        self.samples: List[Sample] = []

        self.wal_path = Path(str(self.db_path) + "-wal")
        self.shm_path = Path(str(self.db_path) + "-shm")

    # -- đo ------------------------------------------------------------- #
    def _measure(self, elapsed: float, write_ms: float, db_first_bytes: int) -> Sample:
        db_bytes = _file_size(self.db_path)
        wal_bytes = _file_size(self.wal_path)
        shm_bytes = _file_size(self.shm_path)

        s = Sample(
            elapsed_s=round(elapsed, 1),
            timestamp_iso=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            db_bytes=db_bytes,
            wal_bytes=wal_bytes,
            shm_bytes=shm_bytes,
            total_bytes=db_bytes + wal_bytes + shm_bytes,
            rss_bytes=_rss_bytes(),
            heap_bytes=_heap_bytes(),
            threads=_thread_count(),
            write_ms=round(write_ms, 3),
            db_growth_mb=round((db_bytes - db_first_bytes) / (1024 * 1024), 4),
            wal_growth_mb=round(wal_bytes / (1024 * 1024), 4),
        )
        try:
            import sqlite3

            # Phải `close()` thật sự — `with sqlite3.connect(...)` chỉ quản lý
            # transaction, không đóng connection.
            conn = sqlite3.connect(str(self.db_path))
            try:
                s.raw_rows = conn.execute("SELECT COUNT(*) FROM telemetry_raw").fetchone()[0]
                s.hourly_rows = conn.execute("SELECT COUNT(*) FROM telemetry_hourly").fetchone()[0]
                s.event_rows = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            finally:
                conn.close()
        except Exception:
            pass
        return s

    # -- chạy ------------------------------------------------------------ #
    def run(self) -> Verdict:
        start = time.time()
        db_first_bytes = _file_size(self.db_path)

        print("=" * 72)
        print("  PC Agent — SOAK TEST")
        print("=" * 72)
        print(f"  DB          : {self.db_path}")
        print(f"  Thời lượng  : {self.duration_s:.0f}s ({self.duration_s / 3600:.2f} giờ)")
        print(f"  Chu kỳ đo   : {self.interval_s:.0f}s")
        print(f"  Tốc độ ghi  : {self.rate} mẫu/chu kỳ")
        print("=" * 72)
        print(f"{'elapsed':>9} {'DB':>11} {'WAL':>11} {'SHM':>9} "
              f"{'raw rows':>10} {'RSS':>10} {'write ms':>9}")
        print("-" * 72)

        next_write = start
        while True:
            now = time.time()
            elapsed = now - start
            if elapsed >= self.duration_s:
                break

            # --- Ghi dữ liệu (tốc độ nhồi) ---
            write_ms = 0.0
            if now >= next_write:
                t0 = time.perf_counter()
                for _ in range(self.rate):
                    self.store.insert_sample(self.generator.next(self.meter_id))
                write_ms = (time.perf_counter() - t0) * 1000.0
                next_write = now + self.interval_s

            # --- Đo ---
            s = self._measure(elapsed, write_ms, db_first_bytes)
            self.samples.append(s)

            print(f"{s.elapsed_s:>8.0f}s {_fmt_mb(s.db_bytes):>11} "
                  f"{_fmt_mb(s.wal_bytes):>11} {_fmt_mb(s.shm_bytes):>9} "
                  f"{s.raw_rows:>10,} {_fmt_mb(s.rss_bytes):>10} {s.write_ms:>9.2f}")

            # --- Ngủ tới chu kỳ kế tiếp ---
            sleep_for = self.interval_s - (time.time() - now)
            if sleep_for > 0:
                time.sleep(sleep_for)

        # --- Tổng hợp giờ + purge (kiểm tra retention) ---
        try:
            self.store.rollup_hourly()
            self.store.purge_expired(
                raw_days=float(self.thresholds.raw_rows_per_day) / 86_400.0,
                hourly_days=365.0,
            )
        except Exception as exc:
            print(f"  ! rollup/purge lỗi: {exc}")

        final = self._measure(time.time() - start, 0.0, db_first_bytes)
        self.samples.append(final)

        verdict = self._evaluate()
        self._write_reports(verdict)
        self._print_verdict(verdict)
        return verdict

    # -- đánh giá --------------------------------------------------------- #
    def _evaluate(self) -> Verdict:
        v = Verdict(duration_s=self.samples[-1].elapsed_s if self.samples else 0.0)
        th = self.thresholds
        checks: List[Dict[str, Any]] = []

        def check(name: str, ok: bool, value: Any, limit: Any, unit: str = "") -> None:
            checks.append({
                "name": name,
                "ok": bool(ok),
                "value": value,
                "limit": limit,
                "unit": unit,
            })

        if not self.samples:
            v.status = "FAIL"
            v.summary = "Không thu được mẫu đo nào."
            v.checks = checks
            return v

        first, last = self.samples[0], self.samples[-1]
        max_db = max(s.db_bytes for s in self.samples)
        max_wal = max(s.wal_bytes for s in self.samples)
        max_total = max(s.total_bytes for s in self.samples)
        max_rss = max(s.rss_bytes for s in self.samples)
        max_raw_rows = max(s.raw_rows for s in self.samples)

        # 1. Kích thước DB
        check("Kích thước telemetry.db", max_db <= th.db_max_mb * 1024 * 1024,
              round(max_db / 1048576, 2), th.db_max_mb, "MB")
        # 2. Kích thước WAL (quan trọng: phải được checkpoint/truncate)
        check("Kích thước telemetry.db-wal", max_wal <= th.wal_max_mb * 1024 * 1024,
              round(max_wal / 1048576, 2), th.wal_max_mb, "MB")
        # 3. Tổng
        check("Tổng DB + WAL + SHM", max_total <= th.total_max_mb * 1024 * 1024,
              round(max_total / 1048576, 2), th.total_max_mb, "MB")
        # 4. RSS
        check("RSS bộ nhớ", max_rss <= th.rss_max_mb * 1024 * 1024,
              round(max_rss / 1048576, 2), th.rss_max_mb, "MB")

        # 5. Rò rỉ bộ nhớ: so RSS đầu với RSS ở 2/3 thời gian
        idx = int(len(self.samples) * 0.66)
        rss_start = self.samples[0].rss_bytes
        rss_mid = self.samples[idx].rss_bytes if idx < len(self.samples) else last.rss_bytes
        rss_end = last.rss_bytes
        growth_pct = 0.0
        if rss_mid > 0:
            growth_pct = (rss_end - rss_mid) / rss_mid * 100.0
        check("Tăng RSS (2/3 → hết)", growth_pct <= th.rss_growth_pct,
              round(growth_pct, 2), th.rss_growth_pct, "%")
        v.rss_growth_pct = round(growth_pct, 2)

        # 6. Tốc độ phình DB
        hours = max(v.duration_s / 3600.0, 1e-6)
        growth_mb = (last.db_bytes - first.db_bytes) / 1048576
        growth_per_hour = growth_mb / hours
        v.db_growth_mb_per_hour = round(growth_per_hour, 4)
        # Ngân sách: nếu DB vượt ngưỡng trong < 1 giờ → phình vô hạn.
        remaining = th.total_max_mb - (last.total_bytes / 1048576)
        projected_hours = remaining / growth_per_hour if growth_per_hour > 0.001 else float("inf")
        check("Thời gian còn đủ trước khi đầy", projected_hours >= 24,
              ("vô hạn" if projected_hours == float("inf") else f"{projected_hours:.1f}h"),
              ">= 24h")

        # 7. Số dòng raw tăng tuyến tính (retention phải có tác dụng)
        check("Số dòng telemetry_raw", max_raw_rows <= th.raw_rows_per_day * 2,
              max_raw_rows, th.raw_rows_per_day * 2, "rows")

        failed = [c for c in checks if not c["ok"]]
        # Cảnh báo (chưa fail) khi RSS tăng vượt 70% ngưỡng — cần theo dõi.
        warns: List[Dict[str, Any]] = []
        for c in checks:
            if c["ok"] and c["name"] == "Tăng RSS (2/3 → hết)":
                if isinstance(c["value"], (int, float)) and c["value"] > 0.7 * th.rss_growth_pct:
                    warns.append(c)
        if failed:
            v.status = "FAIL"
        elif warns:
            v.status = "WARN"
        else:
            v.status = "PASS"

        v.checks = checks
        if v.status == "PASS":
            v.summary = (
                f"Không rò rỉ phát hiện trong {v.duration_s / 3600:.2f}h. "
                f"DB tăng {growth_per_hour:.3f} MB/h, RSS tăng {v.rss_growth_pct}%, "
                f"WAL cao nhất {max_wal / 1048576:.2f} MB."
            )
        elif v.status == "WARN":
            v.summary = (
                f"Có dấu hiệu rò bộ nhớ nhẹ (RSS +{v.rss_growth_pct}%) trong "
                f"{v.duration_s / 3600:.2f}h — cần theo dõi thêm."
            )
        else:
            v.summary = (
                "FAIL: " + "; ".join(
                    f"{c['name']} = {c['value']} (vượt {c['limit']}{c['unit']})"
                    for c in failed
                )
            )
        return v

    # -- báo cáo ---------------------------------------------------------- #
    def _write_reports(self, verdict: Verdict) -> None:
        out_dir = self.db_path.parent
        json_path = out_dir / "soak_report.json"
        csv_path = out_dir / "soak_report.csv"

        payload = {
            "db_path": str(self.db_path),
            "duration_s": verdict.duration_s,
            "interval_s": self.interval_s,
            "rate": self.rate,
            "meter_id": self.meter_id,
            "thresholds": asdict(self.thresholds),
            "verdict": asdict(verdict),
            "samples": [asdict(s) for s in self.samples],
        }
        json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

        if self.samples:
            with csv_path.open("w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=list(asdict(self.samples[0]).keys()))
                writer.writeheader()
                for s in self.samples:
                    writer.writerow(asdict(s))

        print(f"\n  Báo cáo JSON : {json_path}")
        print(f"  Báo cáo CSV  : {csv_path}")

    def _print_verdict(self, v: Verdict) -> None:
        icon = {"PASS": "[ OK ]", "WARN": "[WARN]", "FAIL": "[FAIL]"}.get(v.status, "[????]")
        print()
        print("=" * 72)
        print(f"  KẾT LUẬN SOAK TEST: {icon} {v.status}")
        print("=" * 72)
        for c in v.checks:
            mark = "✓" if c["ok"] else "✗"
            print(f"  {mark} {c['name']:<32} {str(c['value']):>12} "
                  f"(giới hạn {c['limit']}{c['unit']})")
        print("-" * 72)
        print(f"  {v.summary}")
        print("=" * 72)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Soak test PC Agent — đo kích thước DB/WAL và rò rỉ bộ nhớ.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Ví dụ:\n"
               "  python pc_agent/tools/soak_test.py --duration 86400 --interval 300\n"
               "  python pc_agent/tools/soak_test.py --duration 120 --interval 10 --rate 5\n",
    )
    p.add_argument("--db", type=Path, default=None,
                   help="Đường dẫn file DB (mặc định: db trong thư mục dữ liệu agent)")
    p.add_argument("--duration", type=float, default=300.0,
                   help="Thời lượng soak tính bằng giây (mặc định: 300 = 5 phút)")
    p.add_argument("--interval", type=float, default=30.0,
                   help="Chu kỳ ghi mẫu + đo (giây, mặc định: 30)")
    p.add_argument("--rate", type=int, default=1,
                   help="Số mẫu ghi mỗi chu kỳ (mặc định: 1)")
    p.add_argument("--meter-id", default="pdu-01", help="Meter ID (mặc định: pdu-01)")
    p.add_argument("--out-dir", type=Path, default=None,
                   help="Thư mục ghi báo cáo (mặc định: cạnh file DB)")

    # Ngưỡng
    g = p.add_argument_group("ngưỡng")
    g.add_argument("--db-max-mb", type=float, default=200.0)
    g.add_argument("--wal-max-mb", type=float, default=64.0)
    g.add_argument("--total-max-mb", type=float, default=256.0)
    g.add_argument("--rss-max-mb", type=float, default=512.0)
    g.add_argument("--rss-growth-pct", type=float, default=20.0)
    return p.parse_args(argv)


def default_db_path() -> Path:
    """Đường dẫn DB mặc định — dùng đúng logic của agent."""
    try:
        from pc_agent.config import data_dir

        return Path(data_dir()) / "telemetry.db"
    except Exception:
        return Path.cwd() / "soak_data" / "telemetry.db"


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    db_path = args.db or default_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    thresholds = Thresholds(
        db_max_mb=args.db_max_mb,
        wal_max_mb=args.wal_max_mb,
        total_max_mb=args.total_max_mb,
        rss_max_mb=args.rss_max_mb,
        rss_growth_pct=args.rss_growth_pct,
    )

    test = SoakTest(
        db_path=db_path,
        duration_s=args.duration,
        interval_s=args.interval,
        rate=args.rate,
        thresholds=thresholds,
        meter_id=args.meter_id,
    )
    verdict = test.run()

    if args.out_dir:
        args.out_dir.mkdir(parents=True, exist_ok=True)
        for name in ("soak_report.json", "soak_report.csv"):
            src = db_path.parent / name
            if src.exists():
                (args.out_dir / name).write_bytes(src.read_bytes())

    return 0 if verdict.status in ("PASS", "WARN") else 1


if __name__ == "__main__":
    raise SystemExit(main())
