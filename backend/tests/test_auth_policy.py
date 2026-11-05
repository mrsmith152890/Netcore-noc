from app.core.auth import required_role

def test_default_get_is_viewer():
    assert required_role("GET", "/devices") == "viewer"

def test_default_write_is_admin():
    assert required_role("POST", "/devices") == "admin"
    assert required_role("PATCH", "/devices/3") == "admin"

def test_alert_ack_is_operator():
    assert required_role("POST", "/alerts/12/ack") == "operator"

def test_silences_are_operator():
    assert required_role("POST", "/alerts/silences") == "operator"
    assert required_role("POST", "/alerts/silences/3/expire") == "operator"

def test_rules_and_channels_are_admin():
    assert required_role("POST", "/alerts/rules") == "admin"
    assert required_role("PATCH", "/alerts/rules/1") == "admin"
    assert required_role("POST", "/alerts/channels") == "admin"

def test_maps_read_viewer_write_operator():
    assert required_role("GET", "/maps/1") == "viewer"
    assert required_role("PUT", "/maps/1/layout") == "operator"
    assert required_role("DELETE", "/maps/1") == "operator"

def test_users_and_audit_are_admin_only():
    assert required_role("GET", "/auth/users") == "admin"
    assert required_role("GET", "/audit") == "admin"
    assert required_role("POST", "/auth/users") == "admin"
    assert required_role("GET", "/auth/me") == "viewer"

def test_discovery_scan_operator_import_admin():
    assert required_role("POST", "/discovery/scopes/2/runs") == "operator"
    assert required_role("POST", "/discovery/runs/5/import") == "admin"
    assert required_role("POST", "/discovery/scopes") == "admin"

def test_logout_and_password_for_any_role():
    assert required_role("POST", "/auth/logout") == "viewer"
    assert required_role("POST", "/auth/password") == "viewer"

def test_services_policy():
    assert required_role("GET", "/services") == "viewer"
    assert required_role("POST", "/services") == "admin"
    assert required_role("DELETE", "/services/3") == "admin"
    assert required_role("POST", "/services/3/recheck") == "operator"
