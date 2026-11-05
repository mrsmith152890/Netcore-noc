from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Device, DeviceMetric, PingSample, StatusEvent

router = APIRouter(tags=["metrics"])

class MetricOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    sampled_at: datetime
    cpu_pct: float | None
    mem_pct: float | None
    mem_used: int | None
    mem_total: int | None

class PingHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    checked_at: datetime
    success: bool
    rtt_ms: float | None
    packet_loss: float

class StatusEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    at: datetime
    from_state: str
    to_state: str

@router.get("/devices/{device_id}/ping-history", response_model=list[PingHistoryOut])
def device_ping_history(device_id: int, minutes: int = Query(60, ge=1, le=10080),
                        db: Session = Depends(get_db)):
    if not db.get(Device, device_id):
        raise HTTPException(404, "Dispositivo no encontrado")
    since = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    rows = db.scalars(select(PingSample)
                      .where(PingSample.device_id == device_id, PingSample.checked_at >= since)
                      .order_by(PingSample.checked_at.desc()).limit(1200)).all()
    return list(reversed(rows))

@router.get("/devices/{device_id}/events", response_model=list[StatusEventOut])
def device_status_events(device_id: int, limit: int = Query(30, ge=1, le=200),
                         db: Session = Depends(get_db)):
    if not db.get(Device, device_id):
        raise HTTPException(404, "Dispositivo no encontrado")
    return db.scalars(select(StatusEvent).where(StatusEvent.device_id == device_id)
                      .order_by(StatusEvent.at.desc()).limit(limit)).all()

@router.get("/devices/{device_id}/metrics", response_model=list[MetricOut])
def device_metrics(device_id: int, minutes: int = Query(60, ge=1, le=10080),
                   db: Session = Depends(get_db)):
    if not db.get(Device, device_id):
        raise HTTPException(404, "Dispositivo no encontrado")
    since = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    return db.scalars(select(DeviceMetric)
                      .where(DeviceMetric.device_id == device_id, DeviceMetric.sampled_at >= since)
                      .order_by(DeviceMetric.sampled_at)).all()
