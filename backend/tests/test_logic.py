from app.modules.monitoring.rates import counter_rate_bps
from app.modules.monitoring.state import apply_result

def test_transient_failure_keeps_state():
    assert apply_result("UP", 0, False, 3) == ("UP", 1)
    assert apply_result("UP", 1, False, 3) == ("UP", 2)

def test_down_after_threshold():
    assert apply_result("UP", 2, False, 3) == ("DOWN", 3)

def test_recovery():
    assert apply_result("DOWN", 5, True, 3) == ("UP", 0)

def test_unknown_stays_until_threshold():
    assert apply_result("UNKNOWN", 0, False, 3) == ("UNKNOWN", 1)

def test_rate_simple():
    assert counter_rate_bps(1000, 2000, 10, 64) == 800.0

def test_rate_wrap_32():
    assert counter_rate_bps(2**32 - 500, 500, 10, 32) == 800.0

def test_rate_reset_64():
    assert counter_rate_bps(5000, 100, 10, 64) is None

def test_rate_first_sample():
    assert counter_rate_bps(None, 100, 10, 64) is None
