import ipaddress

from app.loadtest import ip_alive, ip_dead

def test_loadtest_ips_are_unique_loopback_addresses():
    ips = [ip_alive(i) for i in range(3000)] + [ip_dead(i) for i in range(3000)]
    assert len(set(ips)) == len(ips)
    assert all(ipaddress.ip_address(ip).is_loopback for ip in ips)
