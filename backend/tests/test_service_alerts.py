from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS

from app.modules.alerts.engine import check_services

NOW = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)

def svc(name="Web", kind="http", state="UP", age=10, error=None, interval=60):
    return NS(name=name, kind=kind, state=state, last_error=error, interval_s=interval,
              last_check_at=NOW - timedelta(seconds=age))

def test_down_service_gives_condition_and_detail():
    cond, detail = check_services([svc(state="DOWN", error="HTTP 503")], None, NOW)
    assert cond is True and "Web" in detail and "HTTP 503" in detail

def test_all_up_is_false():
    assert check_services([svc()], None, NOW) == (False, None)

def test_kind_filter():
    services = [svc(name="DNS", kind="dns", state="DOWN", error="Timeout"), svc(kind="http")]
    assert check_services(services, "http", NOW) == (False, None)
    cond, _ = check_services(services, "dns", NOW)
    assert cond is True

def test_stale_or_unknown_gives_no_data():
    assert check_services([svc(state="DOWN", age=3600)], None, NOW) == (None, None)
    assert check_services([svc(state="UNKNOWN")], None, NOW) == (None, None)

def test_no_services_gives_no_data():
    assert check_services([], None, NOW) == (None, None)
