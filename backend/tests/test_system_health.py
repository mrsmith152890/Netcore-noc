from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.modules.system.health import (cert_ok, decide, disk_ok, expected_ages, format_system_message,
                                       heartbeat_ok)

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)

def d(state="bad", bad=2, ok=0, notified=None, last_notified=None, last_attempt=None):
    return decide(state, bad, ok, notified, last_notified, last_attempt, NOW, confirm=2, remind_s=21600)

def test_heartbeat_states():
    assert heartbeat_ok(NOW, None, 60)[0] is False
    assert heartbeat_ok(NOW, NOW - timedelta(seconds=10), 60)[0] is True
    ok, detail = heartbeat_ok(NOW, NOW - timedelta(seconds=600), 60)
    assert not ok and "sin latido" in detail

def test_disk_thresholds():
    ok, detail = disk_ok({"/": 60.0, "/var/backups": 60.0}, 85)
    assert ok and "60 %" in detail
    ok, detail = disk_ok({"/": 91.0}, 85)
    assert not ok and "91 %" in detail

def test_certificate_thresholds():
    assert cert_ok(None, 30)[0]
    assert not cert_ok(10, 30)[0]
    assert cert_ok(100, 30)[0]

def test_expected_ages():
    ages = expected_ages(settings)
    assert ages["backup"] == 26 * 3600
    assert set(ages) == {"availability", "snmp", "services", "alerts", "discovery", "backup", "restore_test"}

def test_decide_requires_confirmation():
    assert d(bad=1) is None

def test_decide_announces_and_reminds():
    assert d() == "bad"
    assert d(notified="bad", last_notified=NOW - timedelta(hours=1)) is None
    assert d(notified="bad", last_notified=NOW - timedelta(hours=7)) == "reminder"

def test_decide_respects_retry_spacing():
    assert d(last_attempt=NOW - timedelta(seconds=10)) is None
    assert d(last_attempt=NOW - timedelta(seconds=120)) == "bad"

def test_decide_recovery_needs_two_ok():
    assert d("ok", bad=0, ok=1, notified="bad") is None
    assert d("ok", bad=0, ok=2, notified="bad") == "ok"

def test_decide_silent_when_never_notified():
    assert d("ok", bad=0, ok=5, notified=None) is None
    assert d("ok", bad=0, ok=5, notified="ok") is None

def test_system_messages():
    bad = format_system_message("bad", "API", "no responde", NOW, NOW)
    assert "API" in bad and "no responde" in bad
    ok = format_system_message("ok", "API", "", NOW - timedelta(minutes=5), NOW)
    assert "RECUPERADO" in ok and "5 min" in ok
