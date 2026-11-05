from app.modules.discovery.classify import classify

def test_mikrotik_router():
    assert classify(".1.3.6.1.4.1.14988.1", "RouterOS RB750Gr3") == ("MikroTik", "router")

def test_mikrotik_crs_switch():
    assert classify(".1.3.6.1.4.1.14988.1", "RouterOS CRS326-24G-2S+") == ("MikroTik", "switch")

def test_fortigate():
    assert classify(".1.3.6.1.4.1.12356.101.1.1", "FortiGate-60F") == ("Fortinet", "firewall")

def test_cisco_switch():
    assert classify(".1.3.6.1.4.1.9.6.1.83.28.1", "SG300-28 28-Port Gigabit Managed Switch") == ("Cisco", "switch")

def test_linux_server():
    assert classify(".1.3.6.1.4.1.8072.3.2.10", "Linux router-demo-01 6.8.0 #1 SMP") == ("Linux", "server")

def test_pfsense():
    assert classify(".1.3.6.1.4.1.8072.3.2.8", "FreeBSD pfsense.local 14.0 pfSense") == ("pfSense", "firewall")

def test_unknown_enterprise_not_confused_with_cisco():
    assert classify(".1.3.6.1.4.1.9999.1", "") == (None, "other")

def test_no_data():
    assert classify(None, None) == (None, "other")
