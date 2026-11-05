from app.modules.monitoring.snmp import _by_index, _int, _parse

SAMPLE = """.1.3.6.1.2.1.1.1.0 "Linux host 6.8
segunda línea"
.1.3.6.1.2.1.2.2.1.2.1 lo
.1.3.6.1.2.1.2.2.1.2.2 ens18
.1.3.6.1.2.1.2.2.1.8.2 up(1)
.1.3.6.1.2.1.25.3.3.1.2.196608 No Such Instance currently exists at this OID
"""

def test_parse_basic():
    d = _parse(SAMPLE)
    assert d[".1.3.6.1.2.1.2.2.1.2.1"] == "lo"
    assert d[".1.3.6.1.2.1.1.1.0"] == "Linux host 6.8 segunda línea"
    assert ".1.3.6.1.2.1.25.3.3.1.2.196608" not in d

def test_enum_values():
    assert _int("up(1)") == 1
    assert _int("2") == 2
    assert _int("basura") is None

def test_by_index():
    t = _by_index(_parse(SAMPLE), ".1.3.6.1.2.1.2.2.1")
    assert t[1][2] == "lo"
    assert t[2][8] == "up(1)"
