from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import delete, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models import (Alert, AlertRule, Device, DeviceMetric, DeviceStatus, DiscoveredHost,
                        Interface, InterfaceSample, MapNode, NetworkMap, Notification, PingSample,
                        ServiceCheck, ServiceResult, ServiceStatus, Silence, Site, SnmpCredential,
                        SnmpIdentity, StatusEvent)
from app.schemas.device import DeviceCreate, DeviceOut, DeviceUpdate
from app.modules.monitoring.probe import ping
from pydantic import BaseModel

router = APIRouter(prefix="/devices", tags=["devices"])

class DevicePingOut(BaseModel):
    device_id: int
    ip_address: str
    success: bool
    rtt_ms: float | None
    packet_loss: float
    checked_at: str

@router.post("/{device_id}/ping", response_model=DevicePingOut)
async def ping_device(device_id: int, db: Session = Depends(get_db)):
    device = db.get(Device, device_id)
    if not device:
        raise HTTPException(404, "Dispositivo no encontrado")
    result = await ping(device.ip_address, count=3, timeout_s=1)
    return DevicePingOut(device_id=device.id, ip_address=device.ip_address, success=result.success,
                         rtt_ms=result.rtt_ms, packet_loss=result.packet_loss,
                         checked_at=datetime.now(timezone.utc).isoformat())


def _check_site(db: Session, site_id: int):
    if not db.get(Site, site_id):
        raise HTTPException(404, "La sede indicada no existe")

@router.post("", response_model=DeviceOut, status_code=201)
def create_device(payload: DeviceCreate, db: Session = Depends(get_db)):
    _check_site(db, payload.site_id)
    data = payload.model_dump()
    data["ip_address"] = str(payload.ip_address)
    if data.get("wan_gateway_ip") is not None:
        data["wan_gateway_ip"] = str(data["wan_gateway_ip"])
    if data.get("wan_probe_ip") is not None:
        data["wan_probe_ip"] = str(data["wan_probe_ip"])
    device = Device(**data)
    db.add(device)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ya existe un dispositivo con esa IP en la sede")
    db.refresh(device)
    return device

@router.get("", response_model=list[DeviceOut])
def list_devices(site_id: int | None = None, include_disabled: bool = False,
                 db: Session = Depends(get_db)):
    q = select(Device).order_by(Device.name)
    if site_id is not None:
        q = q.where(Device.site_id == site_id)
    if not include_disabled:
        q = q.where(Device.enabled.is_(True))
    return db.scalars(q).all()

@router.get("/{device_id}", response_model=DeviceOut)
def get_device(device_id: int, db: Session = Depends(get_db)):
    device = db.get(Device, device_id)
    if not device:
        raise HTTPException(404, "Dispositivo no encontrado")
    return device

@router.patch("/{device_id}", response_model=DeviceOut)
def update_device(device_id: int, payload: DeviceUpdate, db: Session = Depends(get_db)):
    device = db.get(Device, device_id)
    if not device:
        raise HTTPException(404, "Dispositivo no encontrado")
    data = payload.model_dump(exclude_unset=True)
    if "site_id" in data and data["site_id"] is not None:
        _check_site(db, data["site_id"])
    if data.get("ip_address") is not None:
        data["ip_address"] = str(data["ip_address"])
    for key in ("wan_gateway_ip", "wan_probe_ip"):
        if data.get(key) is not None:
            data[key] = str(data[key])
    for key, value in data.items():
        setattr(device, key, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ya existe un dispositivo con esa IP en la sede")
    db.refresh(device)
    return device


@router.delete("/{device_id}", status_code=204)
def delete_device(device_id: int, request: Request, db: Session = Depends(get_db)):
    """Elimina el inventario y su telemetría, pero conserva referencias históricas de descubrimiento y notificaciones."""
    user = getattr(request.state, "user", None)
    if not user or user.role != "admin":
        raise HTTPException(403, "Solo un administrador puede eliminar dispositivos")

    device = db.get(Device, device_id)
    if not device:
        raise HTTPException(404, "Dispositivo no encontrado")

    map_names = db.scalars(
        select(NetworkMap.name)
        .join(MapNode, MapNode.map_id == NetworkMap.id)
        .where(MapNode.device_id == device_id)
        .distinct()
    ).all()
    if map_names:
        raise HTTPException(
            409,
            "El dispositivo sigue agregado a mapas: " + ", ".join(map_names) +
            ". Retíralo de esos mapas antes de eliminarlo."
        )

    try:
        rule_ids = list(db.scalars(select(AlertRule.id).where(AlertRule.device_id == device_id)))
        alert_filter = Alert.device_id == device_id
        if rule_ids:
            alert_filter = or_(alert_filter, Alert.rule_id.in_(rule_ids))
        alert_ids = list(db.scalars(select(Alert.id).where(alert_filter)))
        if alert_ids:
            db.execute(update(Notification).where(Notification.alert_id.in_(alert_ids))
                       .values(alert_id=None))
            db.execute(delete(Alert).where(Alert.id.in_(alert_ids)))

        silence_filter = Silence.device_id == device_id
        if rule_ids:
            silence_filter = or_(silence_filter, Silence.rule_id.in_(rule_ids))
        db.execute(delete(Silence).where(silence_filter))
        db.execute(delete(AlertRule).where(AlertRule.device_id == device_id))

        check_ids = list(db.scalars(select(ServiceCheck.id).where(ServiceCheck.device_id == device_id)))
        if check_ids:
            db.execute(delete(ServiceStatus).where(ServiceStatus.check_id.in_(check_ids)))
            db.execute(delete(ServiceResult).where(ServiceResult.check_id.in_(check_ids)))
            db.execute(delete(ServiceCheck).where(ServiceCheck.id.in_(check_ids)))

        interface_ids = list(db.scalars(select(Interface.id).where(Interface.device_id == device_id)))
        if interface_ids:
            db.execute(delete(InterfaceSample).where(InterfaceSample.interface_id.in_(interface_ids)))
            db.execute(delete(Interface).where(Interface.id.in_(interface_ids)))

        db.execute(update(DiscoveredHost)
                   .where(DiscoveredHost.device_id == device_id)
                   .values(device_id=None, status="new"))
        db.execute(delete(DeviceStatus).where(DeviceStatus.device_id == device_id))
        db.execute(delete(PingSample).where(PingSample.device_id == device_id))
        db.execute(delete(StatusEvent).where(StatusEvent.device_id == device_id))
        db.execute(delete(DeviceMetric).where(DeviceMetric.device_id == device_id))
        db.execute(delete(SnmpIdentity).where(SnmpIdentity.device_id == device_id))
        db.execute(delete(SnmpCredential).where(SnmpCredential.device_id == device_id))
        db.delete(device)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "No se pudo eliminar el dispositivo por una referencia activa")
