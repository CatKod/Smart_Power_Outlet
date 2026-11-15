"""Test cho các module Giai đoạn 1: auth, version, rate_limit, backup, notifiers, rules.

Chuyển từ script tự kiểm sang **pytest chuẩn** để `pytest tests -q` thu được
đủ test (trước đây các hàm không tên `test_*` nên pytest bỏ qua, chỉ chạy
được bằng `python tests/test_stage1.py`).
"""

from __future__ import annotations

import logging
import os
import sqlite3
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pc_agent.auth import (  # noqa: E402
    ensure_token, generate_token, is_loopback, verify_token,
)
from pc_agent.backup import (  # noqa: E402
    backup_database, prune_old_backups, run_backup,
)
from pc_agent.config import AgentConfig, ConfigStore  # noqa: E402
from pc_agent.core.rules import (  # noqa: E402
    EVENT_OVER_CURRENT, EVENT_OVER_POWER, RuleEngine,
)
from pc_agent.notifiers import NotifierDispatcher  # noqa: E402
from pc_agent.rate_limit import RateLimitFilter  # noqa: E402
from pc_agent.storage.sqlite_store import TelemetryStore  # noqa: E402
from pc_agent.version import version_info  # noqa: E402


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture()
def tmp_env(tmp_path, monkeypatch):
    """Thư mục tạm + trỏ SMARTPOWER_CONFIG_DIR vào đó."""
    monkeypatch.setenv("SMARTPOWER_CONFIG_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture()
def store(tmp_env):
    return ConfigStore(tmp_env / "config.json")


# --------------------------------------------------------------------------- #
# AUTH (A-8-6)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1"])
def test_is_loopback_true(host):
    assert is_loopback(host) is True


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.5", "10.0.0.1"])
def test_is_loopback_false(host):
    assert is_loopback(host) is False


def test_verify_token_none_config_allows():
    """Không cấu hình token → không chặn (chế độ loopback)."""
    assert verify_token(None, "x") is True


def test_verify_token_wrong():
    assert verify_token("abc", "xyz") is False


def test_verify_token_correct():
    assert verify_token("abc", "abc") is True


def test_generate_token_length():
    assert len(generate_token()) >= 32


def test_generate_token_unique():
    assert generate_token() != generate_token()


def test_ensure_token_creates_and_persists(tmp_env, store):
    cfg = AgentConfig(api_host="0.0.0.0")
    tok = ensure_token(cfg, store)
    assert tok
    assert cfg.api_token == tok
    assert (tmp_env / "api_token.txt").exists()
    assert (tmp_env / "api_token.txt").read_text().strip() == tok


def test_ensure_token_is_stable(tmp_env, store):
    cfg = AgentConfig(api_host="0.0.0.0")
    t1 = ensure_token(cfg, store)
    t2 = ensure_token(cfg, store)
    assert t1 == t2


def test_ensure_token_force_new(tmp_env, store):
    cfg = AgentConfig(api_host="0.0.0.0")
    t1 = ensure_token(cfg, store)
    t3 = ensure_token(cfg, store, force_new=True)
    assert t3 != t1
    assert cfg.api_token == t3


def test_ensure_token_loopback_not_required(tmp_env, store):
    cfg = AgentConfig(api_host="127.0.0.1")
    ensure_token(cfg, store)
    assert cfg.api_token is None


# --------------------------------------------------------------------------- #
# VERSION (A-9-3)
# --------------------------------------------------------------------------- #
def test_version_info_fields():
    vi = version_info()
    for key in ("version", "git_commit", "build_time", "python"):
        assert key in vi
    assert vi["git_commit"]
    assert vi["version"]


# --------------------------------------------------------------------------- #
# RATE LIMIT (A-9-2)
# --------------------------------------------------------------------------- #
def _mkrec(msg, name="t", level=logging.WARNING):
    return logging.LogRecord(name, level, "f.py", 1, msg, None, None)


def test_rate_limit_suppresses_repeat():
    flt = RateLimitFilter(window_s=60.0)
    assert flt.filter(_mkrec("Loi doc PZEM: khong phan hoi")) is True
    assert flt.filter(_mkrec("Loi doc PZEM: khong phan hoi")) is False
    assert flt.filter(_mkrec("Loi doc PZEM: khong phan hoi")) is False


def test_rate_limit_allows_different_message():
    flt = RateLimitFilter(window_s=60.0)
    flt.filter(_mkrec("Loi A"))
    assert flt.filter(_mkrec("Loi B")) is True


def test_rate_limit_other_logger_passes():
    flt = RateLimitFilter(window_s=60.0)
    flt.filter(_mkrec("Loi doc PZEM"))
    assert flt.filter(_mkrec("Loi doc PZEM", name="other")) is True


def test_rate_limit_stats():
    flt = RateLimitFilter(window_s=60.0)
    flt.filter(_mkrec("X"))
    flt.filter(_mkrec("X"))
    flt.filter(_mkrec("X"))
    assert flt.stats()["suppressed_total"] == 2


# --------------------------------------------------------------------------- #
# BACKUP (A-9-4)
# --------------------------------------------------------------------------- #
@pytest.fixture()
def sample_db(tmp_path):
    db = tmp_path / "telemetry.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE t (a INTEGER)")
    conn.execute("INSERT INTO t VALUES (1)")
    conn.commit()
    conn.close()
    return db


def test_backup_database_creates_readable_file(tmp_path, sample_db):
    ok = backup_database(sample_db, tmp_path / "bk" / "telemetry-test.db")
    assert ok
    out = tmp_path / "bk" / "telemetry-test.db"
    assert out.exists()
    c2 = sqlite3.connect(str(out))
    try:
        assert c2.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 1
    finally:
        c2.close()


def test_run_backup_writes_both(tmp_path, sample_db):
    cfg = AgentConfig(meter_id="m1")
    res = run_backup(cfg, db_path=sample_db, config_dir=tmp_path, keep=2)
    assert res["db_ok"]
    assert res["config_ok"]
    files = list((tmp_path / "backup").iterdir())
    assert len(files) >= 2


def test_prune_old_backups(tmp_path):
    bdir = tmp_path / "backup"
    bdir.mkdir()
    for i in range(5):
        p = bdir / f"config-old{i}.json"
        p.write_text("{}")
        os.utime(p, (time.time() - 1000 * i, time.time() - 1000 * i))
    removed = prune_old_backups(bdir, keep=2)
    assert removed > 0
    assert len(sorted(bdir.glob("config-*.json"))) <= 2


# --------------------------------------------------------------------------- #
# NOTIFIERS (A-7-7)
# --------------------------------------------------------------------------- #
class FakeNotifier:
    name = "fake"

    def __init__(self, fail=False):
        self.received = []
        self.fail = fail

    def send(self, title, message, severity="critical"):
        self.received.append((title, message, severity))
        return not self.fail


def test_dispatcher_delivers():
    fn = FakeNotifier()
    disp = NotifierDispatcher([fn])
    disp.start()
    try:
        disp.notify("Tieu de", "Noi dung", "critical")
        time.sleep(0.4)
    finally:
        disp.stop()
    assert len(fn.received) == 1
    assert fn.received[0][1] == "Noi dung"


def test_dispatcher_survives_failing_notifier():
    fn = FakeNotifier(fail=True)
    disp = NotifierDispatcher([fn])
    disp.start()
    try:
        disp.notify("T", "M")
        time.sleep(0.4)
        stats = disp.stats()
    finally:
        disp.stop()
    assert stats["failed"] == 1


# --------------------------------------------------------------------------- #
# RULES (A-7-6)
# --------------------------------------------------------------------------- #
@pytest.fixture()
def rules_store(tmp_path):
    return TelemetryStore(tmp_path / "rules.db", "m1")


def test_over_power_and_over_current_fire(rules_store):
    cfg = AgentConfig(power_threshold_w=1000, current_threshold_a=5.0,
                      voltage_min_v=198.0, voltage_max_v=242.0)
    rules = RuleEngine(cfg, rules_store)
    fired = rules.evaluate({
        "power_w": 1500.0, "voltage_v": 220.0, "current_a": 7.0,
        "alarm_active": False,
    })
    types = [f["type"] for f in fired]
    assert EVENT_OVER_POWER in types
    assert EVENT_OVER_CURRENT in types


def test_events_persisted(rules_store):
    cfg = AgentConfig(power_threshold_w=1000, current_threshold_a=5.0,
                      voltage_min_v=198.0, voltage_max_v=242.0)
    rules = RuleEngine(cfg, rules_store)
    rules.evaluate({
        "power_w": 1500.0, "voltage_v": 220.0, "current_a": 7.0,
        "alarm_active": False,
    })
    evt_types = {e["event_type"] for e in rules_store.query_events(limit=10)}
    assert EVENT_OVER_CURRENT in evt_types


def test_event_auto_resolves(rules_store):
    cfg = AgentConfig(power_threshold_w=1000, current_threshold_a=5.0,
                      voltage_min_v=198.0, voltage_max_v=242.0)
    rules = RuleEngine(cfg, rules_store)
    rules.evaluate({"power_w": 1500.0, "voltage_v": 220.0, "current_a": 7.0,
                    "alarm_active": False})
    fired2 = rules.evaluate({"power_w": 100.0, "voltage_v": 220.0, "current_a": 1.0,
                             "alarm_active": False})
    assert EVENT_OVER_POWER not in [f["type"] for f in fired2]
    assert len(rules_store.query_events(active_only=True, limit=10)) == 0


def test_current_below_threshold_does_not_fire(rules_store):
    cfg = AgentConfig(power_threshold_w=1000, current_threshold_a=50.0)
    rules = RuleEngine(cfg, rules_store)
    fired = rules.evaluate({"power_w": 100.0, "voltage_v": 220.0, "current_a": 7.0,
                            "alarm_active": False})
    assert EVENT_OVER_CURRENT not in [f["type"] for f in fired]


# --------------------------------------------------------------------------- #
# STORE — rò connection (phát hiện bởi soak test A-6-6)
# --------------------------------------------------------------------------- #
def test_store_does_not_leak_connections(tmp_path):
    """Ghi nhiều lần rồi gọi rollup/purge → không được "database is locked".

    Trước đây `with sqlite3.connect(...)` không đóng connection khiến
    poller giữ nhiều handle → lock. Bản vá dùng `contextlib.closing`.
    """
    store = TelemetryStore(tmp_path / "leak.db", "m1")
    now = time.time()
    for i in range(20):
        store.insert_sample({
            "timestamp": now + i, "meter_id": "m1", "slave_address": 1,
            "voltage_v": 220.0, "current_a": 1.0, "power_w": 220.0,
            "energy_wh": float(i), "frequency_hz": 50.0,
            "power_factor": 0.95, "alarm_active": False,
        })
    store.rollup_hourly()
    store.purge_expired(raw_days=14.0, hourly_days=365.0)
    store.purge_expired(raw_days=14.0, hourly_days=365.0)
    assert store.stats()["samples"] == 20


def test_store_purge_accepts_float_days(tmp_path):
    """`purge_expired` phải nhận float — công cụ soak test truyền float."""
    store = TelemetryStore(tmp_path / "f.db", "m1")
    store.purge_expired(raw_days=0.5, hourly_days=1.5)
    store.purge_expired(raw_days=14, hourly_days=365)
