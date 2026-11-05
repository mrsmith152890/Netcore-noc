from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.modules.maintenance.retention import cutoff_for, rules

NOW = datetime(2026, 10, 28, tzinfo=timezone.utc)

def test_cutoff():
    assert cutoff_for(NOW, 30) == NOW - timedelta(days=30)

def test_cutoff_never_deletes_everything():
    assert cutoff_for(NOW, 0) == NOW - timedelta(days=1)

def test_rules_reference_real_columns():
    for r in rules(settings):
        assert hasattr(r.model, r.column) and hasattr(r.model, "id"), r.name
