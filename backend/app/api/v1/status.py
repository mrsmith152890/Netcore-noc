from datetime import datetime
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models import Device, DeviceStatus, Site

router = APIRouter(prefix="/status", tags=["status"])

class DeviceStatusOut(BaseModel):
    device_id: int
    site_id: int
    site_name: str
    name: str
    ip_address: str
    device_type: str
    state: str
    consecutive_failures: int
    last_check_at: datetime | None
    last_rtt_ms: float | None
    last_change_at: datetime | None
    wan_gateway_ip: str | None
    wan_probe_ip: str | None
    wan_gateway_state: str | None
    wan_gateway_rtt_ms: float | None
    wan_probe_state: str | None
    wan_probe_rtt_ms: float | None
    wan_checked_at: datetime | None

@router.get("", response_model=list[DeviceStatusOut])
def list_status(db: Session = Depends(get_db)):
    rows = db.execute(
        select(Device, DeviceStatus, Site)
        .join(Site, Site.id == Device.site_id)
        .outerjoin(DeviceStatus, DeviceStatus.device_id == Device.id)
        .where(Device.enabled.is_(True), Site.enabled.is_(True))
        .order_by(Device.name)
    ).all()
    return [
        DeviceStatusOut(
            device_id=d.id, site_id=d.site_id, site_name=site.name,
            name=d.name, ip_address=d.ip_address, device_type=d.device_type,
            state=s.state if s else "UNKNOWN",
            consecutive_failures=s.consecutive_failures if s else 0,
            last_check_at=s.last_check_at if s else None,
            last_rtt_ms=s.last_rtt_ms if s else None,
            last_change_at=s.last_change_at if s else None,
            wan_gateway_ip=d.wan_gateway_ip,
            wan_probe_ip=d.wan_probe_ip,
            wan_gateway_state=s.wan_gateway_state if s else None,
            wan_gateway_rtt_ms=s.wan_gateway_rtt_ms if s else None,
            wan_probe_state=s.wan_probe_state if s else None,
            wan_probe_rtt_ms=s.wan_probe_rtt_ms if s else None,
            wan_checked_at=s.wan_checked_at if s else None,
        )
        for d, s, site in rows
    ]
