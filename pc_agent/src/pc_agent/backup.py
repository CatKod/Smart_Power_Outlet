"""Sao lưu tự động cấu hình + cơ sở dữ liệu (A-9-4).

Vì sao cần:
  - PC Agent chạy 24/7 trong tủ rack. Nếu ổ đĩa hỏng hoặc bị xoá nhầm, mất
    toàn bộ lịch sử telemetry và cấu hình (cổng COM đã nhớ, ngưỡng cảnh báo).
  - Backup phải **tự động**, không ai nhớ chạy tay.

Vì sao KHÔNG copy file DB thô:
  - SQLite ở chế độ WAL có 3 file: `telemetry.db`, `telemetry.db-wal`,
    `telemetry.db-shm`. Copy `telemetry.db` giữa lúc đang ghi sẽ ra một bản
    **không nhất quán** (thiếu dữ liệu trong WAL).
  - Vì vậy dùng **SQLite backup API** (`sqlite3.Connection.backup()`) — SQLite
    tự lo bản ghi nhất quán, kể cả khi có ghi đồng thời.

Sao lưu cấu hình dùng `atomic_write_json` sẵn có — không bao giờ để lại file
JSON hỏng.

Chính sách giữ lại: 7 bản gần nhất (1 tuần backup hằng ngày).
"""

from __future__ import annotations

import logging
import shutil
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

LOG = logging.getLogger("pc_agent.backup")

DEFAULT_KEEP = 7
BACKUP_SUBDIR = "backup"


def backup_dir(config_dir: Path) -> Path:
    return Path(config_dir) / BACKUP_SUBDIR


# --------------------------------------------------------------------------- #
def backup_database(db_path: Path, dest: Path) -> bool:
    """Sao lưu SQLite bằng backup API (nhất quán dù đang ghi).

    Trả `True` nếu thành công.
    """
    db_path = Path(db_path)
    dest = Path(dest)
    if not db_path.exists():
        LOG.warning("Không có file DB %s để sao lưu", db_path)
        return False

    dest.parent.mkdir(parents=True, exist_ok=True)
    # Ghi vào file tạm trước, rồi đổi tên — tránh để lại bản sao dở dang nếu
    # agent bị kill giữa chừng.
    tmp = dest.with_suffix(dest.suffix + ".tmp")

    src = None
    out = None
    try:
        src = sqlite3.connect(str(db_path), timeout=10.0)
        out = sqlite3.connect(str(tmp))
        with out:
            src.backup(out)
        out.close()
        out = None
        src.close()
        src = None
        shutil.move(str(tmp), str(dest))
        LOG.info("Đã sao lưu DB -> %s (%.1f KB)",
                 dest, dest.stat().st_size / 1024)
        return True
    except Exception as exc:  # noqa: BLE001
        LOG.error("Không sao lưu được DB: %s", exc)
        return False
    finally:
        for conn in (src, out):
            if conn is not None:
                try:
                    conn.close()
                except Exception:  # noqa: BLE001
                    pass
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


# --------------------------------------------------------------------------- #
def backup_config(config, dest: Path) -> bool:
    """Sao lưu cấu hình ra file JSON (ghi atomically)."""
    from .config import atomic_write_json

    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(dest, config.to_dict())
        LOG.info("Đã sao lưu cấu hình -> %s", dest)
        return True
    except Exception as exc:  # noqa: BLE001
        LOG.error("Không sao lưu được cấu hình: %s", exc)
        return False


# --------------------------------------------------------------------------- #
def prune_old_backups(directory: Path, keep: int = DEFAULT_KEEP) -> int:
    """Xoá bản backup cũ, chỉ giữ `keep` bản mới nhất. Trả số bản đã xoá."""
    directory = Path(directory)
    if not directory.is_dir():
        return 0

    # Nhóm theo "tiền tố" để cấu hình và DB cùng bị prune đồng bộ.
    groups: Dict[str, list] = {}
    for path in directory.iterdir():
        if not path.is_file():
            continue
        name = path.name
        for prefix in ("config-", "telemetry-"):
            if name.startswith(prefix):
                groups.setdefault(prefix, []).append(path)
                break

    removed = 0
    for paths in groups.values():
        paths.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        for old in paths[keep:]:
            try:
                old.unlink()
                removed += 1
            except OSError:
                pass
    if removed:
        LOG.info("Đã xoá %d bản backup cũ (giữ lại %d bản mới nhất)", removed, keep)
    return removed


# --------------------------------------------------------------------------- #
def run_backup(
    config,
    config_store=None,
    db_path: Optional[Path] = None,
    config_dir: Optional[Path] = None,
    keep: int = DEFAULT_KEEP,
) -> Dict[str, Any]:
    """Chạy một vòng sao lưu đầy đủ (cấu hình + DB)."""
    from .config import config_dir as default_config_dir
    from .config import database_path

    cfg_dir = Path(config_dir) if config_dir else default_config_dir()
    bdir = backup_dir(cfg_dir)
    bdir.mkdir(parents=True, exist_ok=True)

    stamp = time.strftime("%Y%m%d-%H%M%S")
    db_src = Path(db_path) if db_path else database_path()

    result: Dict[str, Any] = {
        "timestamp": stamp,
        "directory": str(bdir),
        "db_ok": False,
        "config_ok": False,
    }

    result["db_ok"] = backup_database(db_src, bdir / f"telemetry-{stamp}.db")
    result["config_ok"] = backup_config(config, bdir / f"config-{stamp}.json")

    prune_old_backups(bdir, keep=keep)
    return result


# --------------------------------------------------------------------------- #
class BackupScheduler:
    """Chạy backup định kỳ trên một thread riêng.

    Thread riêng (không phải thread chính) để một lần backup chậm — ví dụ khi
    ổ đĩa đang bận — **không** làm nghẽn vòng lấy mẫu 1 Hz.
    """

    def __init__(
        self,
        config,
        config_store=None,
        interval_s: float = 86400.0,
        keep: int = DEFAULT_KEEP,
        config_dir: Optional[Path] = None,
    ) -> None:
        self.config = config
        self.config_store = config_store
        self.interval_s = interval_s
        self.keep = keep
        self.config_dir = config_dir
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.last_result: Optional[Dict[str, Any]] = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._loop, name="BackupScheduler", daemon=True
        )
        self._thread.start()
        LOG.info("Đã bật backup tự động (mỗi %.0f giây, giữ %d bản).",
                 self.interval_s, self.keep)

    def stop(self, timeout: float = 5.0) -> None:
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        self._thread = None

    def _loop(self) -> None:
        # Chạy ngay một lần khi khởi động, rồi ngủ theo chu kỳ.
        while not self._stop_event.is_set():
            try:
                self.last_result = run_backup(
                    self.config,
                    config_store=self.config_store,
                    keep=self.keep,
                    config_dir=self.config_dir,
                )
            except Exception as exc:  # noqa: BLE001
                LOG.exception("Lỗi trong luồng backup: %s", exc)
            # Dùng `wait` để dừng được ngay khi được yêu cầu.
            self._stop_event.wait(self.interval_s)
