import logging
import time
from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.database import SessionLocal
from app.models import WorkerHeartbeat

log = logging.getLogger("netcore.heartbeat")
_last: dict[str, float] = {}
MIN_GAP_S = 5

def beat(worker: str, detail: str | None = None, cycle_ms: int | None = None) -> None:
    """Latido de un worker. Es de mejor esfuerzo: nunca debe romper el ciclo que lo llama."""
    t = time.monotonic()
    if t - _last.get(worker, -1e9) < MIN_GAP_S:
        return
    try:
        values = {"beat_at": datetime.now(timezone.utc), "cycle_ms": cycle_ms,
                  "detail": detail[:255] if detail else None}
        with SessionLocal() as db:
            stmt = pg_insert(WorkerHeartbeat).values(worker=worker, **values)
            db.execute(stmt.on_conflict_do_update(index_elements=["worker"], set_=values))
            db.commit()
        _last[worker] = t
    except Exception:
        log.debug("No se pudo registrar el latido de %s", worker, exc_info=True)
