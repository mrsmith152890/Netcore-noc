from datetime import datetime, timedelta, timezone

import pytest

from app.modules.reports.compute import availability_pct, coverage_pct, resolve_range
from app.modules.reports.render import to_csv, to_pdf
from app.modules.reports.schema import AlertsSummary, DeviceRow, PeriodInfo, Report

NOW = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)

def make_report(name="RB-Core"):
    return Report(
        period=PeriodInfo(start=NOW - timedelta(days=7), end=NOW, hours=168, site=None),
        avg_availability_pct=99.9, total_outages=2,
        devices=[DeviceRow(device_id=1, name=name, ip="10.0.0.1", site="Principal",
                           availability_pct=99.9, coverage_pct=100.0, samples=60480, failed=60,
                           outages=2, est_downtime_s=600, avg_rtt_ms=1.5, avg_loss_pct=0.1)],
        services=[], alerts=AlertsSummary(total=0, critical=0, warning=0, mttr_s=None, top_devices=[]),
        alert_rows=[])

def test_availability_pct():
    assert availability_pct(0, 0) is None
    assert availability_pct(1000, 1) == 99.9
    assert availability_pct(10, 10) == 0.0

def test_coverage_pct():
    assert coverage_pct(8640, 86400, 10) == 100.0
    assert coverage_pct(4320, 86400, 10) == 50.0
    assert coverage_pct(99999, 86400, 10) == 100.0

def test_range_default_is_last_days():
    start, end = resolve_range(None, None, 7, NOW)
    assert end == NOW and start == NOW - timedelta(days=7)

def test_range_validation():
    with pytest.raises(ValueError):
        resolve_range(NOW - timedelta(minutes=10), NOW, 7, NOW)
    with pytest.raises(ValueError):
        resolve_range(NOW - timedelta(days=400), NOW, 7, NOW)
    with pytest.raises(ValueError):
        resolve_range(NOW - timedelta(days=1), None, 7, NOW)

def test_csv_spanish_style():
    text = to_csv(make_report(), "devices", "es")
    assert text.startswith("\ufeff")
    header, row = text.lstrip("\ufeff").split("\r\n")[:2]
    assert ";" in header and "99,90" in row

def test_csv_english_style():
    row = to_csv(make_report(), "devices", "en").lstrip("\ufeff").split("\r\n")[1]
    assert row.split(",")[3] == "99.90"

def test_csv_neutralizes_formulas():
    assert "'=HYPERLINK" in to_csv(make_report('=HYPERLINK("http://x")'), "devices", "en")

def test_pdf_is_valid():
    pdf = to_pdf(make_report())
    assert pdf.startswith(b"%PDF") and len(pdf) > 1000
