from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models import SystemStatus, WorkerHeartbeat
from app.modules.system.health import TITLES, check_key, expected_ages, heartbeat_ok

router = APIRouter(prefix="/system", tags=["system"])

class CheckOut(BaseModel):
    key: str
    title: str
    ok: bool
    detail: str | None
    since: datetime
    checked_at: datetime

class HeartbeatOut(BaseModel):
    worker: str
    title: str
    age_s: int | None
    expected_s: int
    ok: bool
    cycle_ms: int | None
    detail: str | None

class SystemOut(BaseModel):
    overall_ok: bool
    problems: int
    watchdog_ok: bool
    watchdog_age_s: int | None
    checks: list[CheckOut]
    heartbeats: list[HeartbeatOut]

@router.get("/status", response_model=SystemOut)
def system_status(db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    rows = db.scalars(select(SystemStatus).order_by(SystemStatus.key)).all()
    beats = {b.worker: b for b in db.scalars(select(WorkerHeartbeat))}

    heartbeats = []
    for worker, expected in expected_ages(settings).items():
        b = beats.get(worker)
        ok, _ = heartbeat_ok(now, b.beat_at if b else None, expected)
        if worker == "restore_test" and b and (b.detail or "").upper().startswith("FALLA"):
            ok = False
        heartbeats.append(HeartbeatOut(
            worker=worker, title=TITLES.get(check_key(worker), worker),
            age_s=int((now - b.beat_at).total_seconds()) if b else None, expected_s=expected,
            ok=ok, cycle_ms=b.cycle_ms if b else None, detail=b.detail if b else None))

    newest = max((r.checked_at for r in rows), default=None)
    watchdog_age = int((now - newest).total_seconds()) if newest else None
    watchdog_ok = watchdog_age is not None and watchdog_age <= settings.watchdog_interval_s * 4
    problems = sum(1 for r in rows if r.state == "bad") + (0 if watchdog_ok else 1)
    return SystemOut(
        overall_ok=problems == 0, problems=problems, watchdog_ok=watchdog_ok, watchdog_age_s=watchdog_age,
        checks=[CheckOut(key=r.key, title=TITLES.get(r.key, r.key), ok=r.state == "ok", detail=r.detail,
                         since=r.since, checked_at=r.checked_at) for r in rows],
        heartbeats=heartbeats)
