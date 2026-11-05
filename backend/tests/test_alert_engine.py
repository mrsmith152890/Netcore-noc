from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS

from app.modules.alerts.engine import (channel_accepts, check_condition, describe, fmt_duration,
                                       format_message, is_silenced)

NOW = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)

def status(state="UP", rtt=5.0, age=5):
    return NS(state=state, last_rtt_ms=rtt, last_check_at=NOW - timedelta(seconds=age))

def metric(cpu=50.0, mem=40.0, age=10):
    return NS(cpu_pct=cpu, mem_pct=mem, sampled_at=NOW - timedelta(seconds=age))

def test_device_down_true():
    assert check_condition("device_down", None, status("DOWN"), None, NOW) == (True, None)

def test_device_up_false():
    assert check_condition("device_down", None, status("UP"), None, NOW) == (False, None)

def test_device_unknown_gives_no_data():
    assert check_condition("device_down", None, status("UNKNOWN"), None, NOW) == (None, None)

def test_stale_probe_gives_no_data():
    assert check_condition("device_down", None, status("DOWN", age=600), None, NOW) == (None, None)

def test_cpu_over_threshold():
    assert check_condition("cpu_high", 90, None, metric(cpu=95.0), NOW) == (True, 95.0)

def test_cpu_stale_gives_no_data():
    assert check_condition("cpu_high", 90, None, metric(age=3600), NOW) == (None, None)

def test_latency_only_evaluated_when_up():
    assert check_condition("latency_high", 100, status("DOWN"), None, NOW) == (None, None)
    assert check_condition("latency_high", 100, status("UP", rtt=250.0), None, NOW) == (True, 250.0)

def test_silence_matching():
    s = NS(rule_id=None, device_id=5, site_id=None,
           starts_at=NOW - timedelta(minutes=1), ends_at=NOW + timedelta(hours=1))
    assert is_silenced([s], 1, 5, 1, NOW)
    assert not is_silenced([s], 1, 6, 1, NOW)
    expired = NS(rule_id=None, device_id=5, site_id=None,
                 starts_at=NOW - timedelta(hours=2), ends_at=NOW - timedelta(seconds=1))
    assert not is_silenced([expired], 1, 5, 1, NOW)

def test_channel_accepts():
    assert channel_accepts("warning", "critical")
    assert channel_accepts("critical", "critical")
    assert not channel_accepts("critical", "warning")

def test_fmt_duration():
    assert fmt_duration(45) == "45 s"
    assert fmt_duration(300) == "5 min"
    assert fmt_duration(7800) == "2 h 10 min"
    assert fmt_duration(100000) == "1 d 3 h"

def test_format_message_firing():
    text = format_message("firing", rule_name="Dispositivo caído", severity="critical",
                          device="RB-Core", ip="10.0.0.1", site="Principal",
                          detail="No responde a ICMP", since=NOW, now=NOW)
    assert "CRÍTICO" in text and "RB-Core" in text and "Desde:" in text

def test_describe():
    assert describe("cpu_high", 90, 95.0) == "CPU al 95 % (umbral 90 %)"
