import pytest
from app.modules.discovery.scope import ScopeError, host_list, validate_cidr

def test_hosts_in_24():
    assert len(host_list(validate_cidr("192.168.1.0/24"))) == 254

def test_single_host():
    assert host_list(validate_cidr("10.0.0.5/32")) == ["10.0.0.5"]

def test_public_rejected():
    with pytest.raises(ScopeError):
        validate_cidr("8.8.8.0/24")

def test_too_big():
    with pytest.raises(ScopeError):
        validate_cidr("10.0.0.0/8")

def test_strict_cidr():
    with pytest.raises(ScopeError):
        validate_cidr("192.168.1.5/24")

def test_ipv6_rejected():
    with pytest.raises(ScopeError):
        validate_cidr("fd00::/64")

def test_this_network_rejected():
    with pytest.raises(ScopeError):
        validate_cidr("0.0.0.0/24")
