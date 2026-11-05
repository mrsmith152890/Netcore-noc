import asyncio
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decrypt, encrypt
from app.models import Device, Interface, InterfaceSample, SnmpCredential, SnmpIdentity
from app.modules.monitoring.snmp import SnmpError, get_identity

router = APIRouter(tags=["snmp"])

class SnmpConfigIn(BaseModel):
    community: str = Field(min_length=1, max_length=128)
    port: int = Field(default=161, ge=1, le=65535)
    enabled: bool = True

class SnmpConfigOut(BaseModel):
    device_id: int
    version: str
    port: int
    enabled: bool
    has_community: bool = True

class SnmpIdentityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    device_id: int
    sys_name: str | None
    sys_descr: str | None
    sys_object_id: str | None
    uptime_s: int | None
    last_poll_at: datetime | None
    last_success_at: datetime | None
    last_error: str | None

class InterfaceOut(BaseModel):
    id: int
    if_index: int
    name: str | None
    descr: str | None
    speed_bps: int | None
    admin_status: str | None
    oper_status: str | None
    monitored: bool
    last_seen_at: datetime | None
    in_bps: float | None
    out_bps: float | None
    last_sample_at: datetime | None

class SampleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    sampled_at: datetime
    in_bps: float | None
    out_bps: float | None
    oper_status: str | None

class InterfaceUpdate(BaseModel):
    monitored: bool

@router.put("/devices/{device_id}/snmp", response_model=SnmpConfigOut)
def put_snmp(device_id: int, payload: SnmpConfigIn, db: Session = Depends(get_db)):
    if not db.get(Device, device_id):
        raise HTTPException(404, "Dispositivo no encontrado")
    cred = db.get(SnmpCredential, device_id)
    if cred is None:
        cred = SnmpCredential(device_id=device_id)
        db.add(cred)
    cred.version = "2c"
    cred.port = payload.port
    cred.enabled = payload.enabled
    cred.community_enc = encrypt(payload.community)
    db.commit()
    return SnmpConfigOut(device_id=device_id, version=cred.version, port=cred.port, enabled=cred.enabled)

@router.get("/devices/{device_id}/snmp", response_model=SnmpConfigOut)
def get_snmp(device_id: int, db: Session = Depends(get_db)):
    cred = db.get(SnmpCredential, device_id)
    if not cred:
        raise HTTPException(404, "SNMP no configurado para este dispositivo")
    return SnmpConfigOut(device_id=device_id, version=cred.version, port=cred.port, enabled=cred.enabled)

@router.post("/devices/{device_id}/snmp/test")
async def test_snmp(device_id: int, db: Session = Depends(get_db)):
    """Prueba puntual y acotada por timeout; el monitoreo continuo lo hace el poller."""
    device = db.get(Device, device_id)
    cred = db.get(SnmpCredential, device_id)
    if not device:
        raise HTTPException(404, "Dispositivo no encontrado")
    if not cred:
        raise HTTPException(404, "SNMP no configurado para este dispositivo")
    ip, port, community = device.ip_address, cred.port, decrypt(cred.community_enc)
    try:
        return await get_identity(ip, port, community)
    except (SnmpError, asyncio.TimeoutError) as e:
        raise HTTPException(502, f"SNMP falló: {e}")

@router.get("/devices/{device_id}/snmp/identity", response_model=SnmpIdentityOut)
def get_identity_info(device_id: int, db: Session = Depends(get_db)):
    ident = db.get(SnmpIdentity, device_id)
    if not ident:
        raise HTTPException(404, "Aún no hay datos SNMP de este dispositivo")
    return ident

@router.get("/devices/{device_id}/interfaces", response_model=list[InterfaceOut])
def list_interfaces(device_id: int, db: Session = Depends(get_db)):
    ifaces = db.scalars(select(Interface).where(Interface.device_id == device_id)
                        .order_by(Interface.if_index)).all()
    latest: dict[int, InterfaceSample] = {}
    if ifaces:
        q = (select(InterfaceSample)
             .where(InterfaceSample.interface_id.in_([i.id for i in ifaces]))
             .distinct(InterfaceSample.interface_id)
             .order_by(InterfaceSample.interface_id, InterfaceSample.sampled_at.desc()))
        latest = {s.interface_id: s for s in db.scalars(q)}
    out = []
    for i in ifaces:
        s = latest.get(i.id)
        out.append(InterfaceOut(
            id=i.id, if_index=i.if_index, name=i.name, descr=i.descr, speed_bps=i.speed_bps,
            admin_status=i.admin_status, oper_status=i.oper_status, monitored=i.monitored,
            last_seen_at=i.last_seen_at,
            in_bps=s.in_bps if s else None, out_bps=s.out_bps if s else None,
            last_sample_at=s.sampled_at if s else None))
    return out

@router.patch("/interfaces/{interface_id}")
def update_interface(interface_id: int, payload: InterfaceUpdate, db: Session = Depends(get_db)):
    iface = db.get(Interface, interface_id)
    if not iface:
        raise HTTPException(404, "Interfaz no encontrada")
    iface.monitored = payload.monitored
    db.commit()
    return {"id": iface.id, "monitored": iface.monitored}

@router.get("/interfaces/{interface_id}/samples", response_model=list[SampleOut])
def interface_samples(interface_id: int, minutes: int = Query(60, ge=1, le=10080),
                      db: Session = Depends(get_db)):
    if not db.get(Interface, interface_id):
        raise HTTPException(404, "Interfaz no encontrada")
    since = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    return db.scalars(select(InterfaceSample)
                      .where(InterfaceSample.interface_id == interface_id,
                             InterfaceSample.sampled_at >= since)
                      .order_by(InterfaceSample.sampled_at)).all()
