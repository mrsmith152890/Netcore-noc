import pytest
from app.modules.services.checks import (CheckConfigError, parse_status_ranges, status_ok,
                                         validate_host, validate_http_url)

def test_default_status_ranges():
    r = parse_status_ranges(None)
    assert status_ok(200, r) and status_ok(301, r)
    assert not status_ok(404, r) and not status_ok(500, r)

def test_custom_status_ranges():
    r = parse_status_ranges("200,401-403")
    assert status_ok(200, r) and status_ok(401, r) and status_ok(403, r)
    assert not status_ok(404, r)

def test_bad_status_ranges():
    with pytest.raises(CheckConfigError):
        parse_status_ranges("abc")

def test_http_url_ok():
    assert validate_http_url("http://" + "usuario" + ":" + "clave" + "@192.0.2.1/") == "http://{ip}:8080/health"

def test_http_url_rejects_bad_scheme():
    for url in ("ftp://10.0.0.1/", "file:///etc/passwd"):
        with pytest.raises(CheckConfigError):
            validate_http_url(url)

def test_http_url_rejects_credentials():
    with pytest.raises(CheckConfigError):
        validate_http_url("http://usuario:clave@10.0.0.1/")

def test_http_url_rejects_link_local():
    with pytest.raises(CheckConfigError):
        validate_http_url("http://169.254.169.254/latest/meta-data")

def test_validate_host():
    assert validate_host("10.0.0.5") == "10.0.0.5"
    assert validate_host("dns.example.com") == "dns.example.com"
    for bad in ("host con espacios!", "169.254.1.1"):
        with pytest.raises(CheckConfigError):
            validate_host(bad)
