import ipaddress
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import encrypt
from app.models import Device, DiscoveredHost, DiscoveryRun, DiscoveryScope, Site, SnmpCredential
from app.modules.discovery.scope import ScopeError, validate_cidr
from app.schemas.device import DeviceType

router = APIRouter(prefix="/discovery", tags=["discovery"])

# ---------- esquemas ----------
class ScopeCreate(BaseModel):
    site_id: int
    cidr: str = Field(min_length=7, max_length=50)
    description: str | None = Field(default=None, max_length=255)
    community: str | None = Field(default=None, max_length=128)
    snmp_port: int = Field(default=161, ge=1, le=65535)
    allow_public: bool = False

class ScopeUpdate(BaseModel):
    description: str | None = Field(default=None, max_length=255)
    community: str | None = Field(default=None, max_length=128)  # vacío = quitar
    enabled: bool | None = None

class ScopeOut(BaseModel):
    id: int
    site_id: int
    cidr: str
    description: str | None
    has_community: bool
    snmp_port: int
    enabled: bool
    allow_public: bool
    created_at: datetime

class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    scope_id: int
    status: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    hosts_total: int
    hosts_scanned: int
    hosts_alive: int
    hosts_snmp: int
    error: str | None

class HostOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    run_id: int
    ip: str
    rtt_ms: float | None
    snmp_ok: bool
    sys_name: str | None
    sys_descr: str | None
    sys_object_id: str | None
    vendor: str | None
    device_type: str
    device_id: int | None
    status: str

class ImportItem(BaseModel):
    host_id: int
    name: str = Field(min_length=1, max_length=100)
    device_type: DeviceType = "other"
    vendor: str | None = Field(default=None, max_length=50)
    model: str | None = Field(default=None, max_length=80)

class ImportIn(BaseModel):
    items: list[ImportItem] = Field(min_length=1)
    enable_snmp: bool = True

class Skipped(BaseModel):
    host_id: int
    reason: str

class ImportResult(BaseModel):
    imported: list[int]
    skipped: list[Skipped]

def _scope_out(s: DiscoveryScope) -> ScopeOut:
    return ScopeOut(id=s.id, site_id=s.site_id, cidr=s.cidr, description=s.description,
                    has_community=bool(s.community_enc), snmp_port=s.snmp_port,
                    enabled=s.enabled, allow_public=s.allow_public, created_at=s.created_at)

def _get_scope(db: Session, scope_id: int) -> DiscoveryScope:
    s = db.get(DiscoveryScope, scope_id)
    if not s:
        raise HTTPException(404, "Rango no encontrado")
    return s

def _get_run(db: Session, run_id: int) -> DiscoveryRun:
    r = db.get(DiscoveryRun, run_id)
    if not r:
        raise HTTPException(404, "Escaneo no encontrado")
    return r

# ---------- rangos autorizados ----------
@router.post("/scopes", response_model=ScopeOut, status_code=201)
def create_scope(payload: ScopeCreate, db: Session = Depends(get_db)):
    if not db.get(Site, payload.site_id):
        raise HTTPException(404, "La sede no existe")
    try:
        net = validate_cidr(payload.cidr, allow_public=payload.allow_public)
    except ScopeError as e:
        raise HTTPException(400, str(e))
    scope = DiscoveryScope(
        site_id=payload.site_id, cidr=str(net), description=payload.description,
        snmp_port=payload.snmp_port,
        community_enc=encrypt(payload.community) if payload.community else None,
        allow_public=payload.allow_public)
    db.add(scope)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ese rango ya está registrado en la sede")
    db.refresh(scope)
    return _scope_out(scope)

@router.get("/scopes", response_model=list[ScopeOut])
def list_scopes(db: Session = Depends(get_db)):
    return [_scope_out(s) for s in db.scalars(
        select(DiscoveryScope).where(DiscoveryScope.enabled.is_(True)).order_by(DiscoveryScope.id))]

@router.patch("/scopes/{scope_id}", response_model=ScopeOut)
def update_scope(scope_id: int, payload: ScopeUpdate, db: Session = Depends(get_db)):
    scope = _get_scope(db, scope_id)
    data = payload.model_dump(exclude_unset=True)
    if "community" in data:
        community = data.pop("community")
        scope.community_enc = encrypt(community) if community else None
    for k, v in data.items():
        setattr(scope, k, v)
    db.commit()
    db.refresh(scope)
    return _scope_out(scope)

@router.delete("/scopes/{scope_id}", status_code=204)
def delete_scope(scope_id: int, db: Session = Depends(get_db)):
    """Revoca el rango sin borrar los escaneos ni los resultados históricos."""
    scope = _get_scope(db, scope_id)
    active = db.scalar(select(DiscoveryRun.id).where(
        DiscoveryRun.scope_id == scope_id,
        DiscoveryRun.status.in_(["pending", "running"])))
    if active:
        raise HTTPException(409, "No se puede eliminar mientras haya un escaneo en curso. Cancela el escaneo e inténtalo de nuevo.")
    scope.enabled = False
    db.commit()
    return Response(status_code=204)

# ---------- escaneos ----------
@router.post("/scopes/{scope_id}/runs", response_model=RunOut, status_code=201)
def create_run(scope_id: int, db: Session = Depends(get_db)):
    """Solo registra la solicitud; el escaneo lo ejecuta el worker de descubrimiento."""
    scope = _get_scope(db, scope_id)
    if not scope.enabled:
        raise HTTPException(400, "El rango está desactivado")
    try:
        validate_cidr(scope.cidr, allow_public=scope.allow_public)
    except ScopeError as e:
        raise HTTPException(400, str(e))
    active = db.scalar(select(DiscoveryRun.id).where(
        DiscoveryRun.scope_id == scope_id, DiscoveryRun.status.in_(["pending", "running"])))
    if active:
        raise HTTPException(409, "Ya hay un escaneo en curso para este rango")
    run = DiscoveryRun(scope_id=scope_id)
    db.add(run)
    db.commit()
    db.refresh(run)
    return run

@router.get("/runs", response_model=list[RunOut])
def list_runs(scope_id: int | None = None, limit: int = Query(20, ge=1, le=100),
              db: Session = Depends(get_db)):
    q = select(DiscoveryRun).order_by(DiscoveryRun.id.desc()).limit(limit)
    if scope_id is not None:
        q = q.where(DiscoveryRun.scope_id == scope_id)
    return db.scalars(q).all()

@router.get("/runs/{run_id}", response_model=RunOut)
def get_run(run_id: int, db: Session = Depends(get_db)):
    return _get_run(db, run_id)

@router.get("/runs/{run_id}/hosts", response_model=list[HostOut])
def run_hosts(run_id: int, db: Session = Depends(get_db)):
    _get_run(db, run_id)
    rows = db.scalars(select(DiscoveredHost).where(DiscoveredHost.run_id == run_id)).all()
    return sorted(rows, key=lambda h: ipaddress.ip_address(h.ip))

@router.post("/runs/{run_id}/cancel", response_model=RunOut)
def cancel_run(run_id: int, db: Session = Depends(get_db)):
    run = _get_run(db, run_id)
    if run.status not in ("pending", "running"):
        raise HTTPException(409, "El escaneo ya terminó")
    run.status, run.finished_at = "cancelled", datetime.now(timezone.utc)
    db.commit()
    db.refresh(run)
    return run

# ---------- importación validada por el usuario ----------
@router.post("/runs/{run_id}/import", response_model=ImportResult)
def import_hosts(run_id: int, payload: ImportIn, db: Session = Depends(get_db)):
    run = _get_run(db, run_id)
    if run.status != "done":
        raise HTTPException(400, "Solo se puede importar de un escaneo terminado")
    scope = _get_scope(db, run.scope_id)
    hosts = {h.id: h for h in db.scalars(select(DiscoveredHost).where(
        DiscoveredHost.run_id == run_id,
        DiscoveredHost.id.in_([i.host_id for i in payload.items])))}

    imported: list[int] = []
    skipped: list[Skipped] = []
    for item in payload.items:
        h = hosts.get(item.host_id)
        if h is None:
            skipped.append(Skipped(host_id=item.host_id, reason="No pertenece a este escaneo"))
            continue
        if h.status != "new":
            skipped.append(Skipped(host_id=h.id, reason=f"{h.ip}: ya estaba registrado o importado"))
            continue
        existing = db.scalar(select(Device.id).where(
            Device.site_id == scope.site_id, Device.ip_address == h.ip))
        if existing:
            h.status, h.device_id = "registered", existing
            skipped.append(Skipped(host_id=h.id, reason=f"{h.ip}: ya existe en el inventario de la sede"))
            continue
        device = Device(site_id=scope.site_id, name=item.name, ip_address=h.ip,
                        device_type=item.device_type, vendor=item.vendor or h.vendor, model=item.model)
        try:
            with db.begin_nested():
                db.add(device)
                db.flush()
        except IntegrityError:
            skipped.append(Skipped(host_id=h.id, reason=f"{h.ip}: duplicado"))
            continue
        if payload.enable_snmp and h.snmp_ok and scope.community_enc:
            db.add(SnmpCredential(device_id=device.id, version="2c", port=scope.snmp_port,
                                  community_enc=scope.community_enc, enabled=True))
        h.status, h.device_id = "imported", device.id
        imported.append(device.id)
    db.commit()
    return ImportResult(imported=imported, skipped=skipped)
