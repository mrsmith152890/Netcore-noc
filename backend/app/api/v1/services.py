import ipaddress
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Device, ServiceCheck, ServiceResult, ServiceStatus
from app.modules.services.checks import (CheckConfigError, parse_status_ranges, validate_dns_name,
                                         validate_host, validate_http_url)

router = APIRouter(prefix="/services", tags=["services"])

Kind = Literal["tcp", "http", "dns"]
DnsType = Literal["A", "AAAA", "MX", "TXT", "CNAME", "NS"]

class ServiceCreate(BaseModel):
    device_id: int
    name: str = Field(min_length=1, max_length=100)
    kind: Kind
    host: str | None = Field(default=None, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    url: str | None = Field(default=None, max_length=500)
    expect_status: str | None = Field(default=None, max_length=50)
    expect_text: str | None = Field(default=None, max_length=200)
    verify_tls: bool = True
    dns_query: str | None = Field(default=None, max_length=255)
    dns_type: DnsType = "A"
    dns_expect: str | None = Field(default=None, max_length=255)
    interval_s: int = Field(default=60, ge=10, le=3600)
    timeout_s: int = Field(default=5, ge=1, le=30)
    fail_threshold: int = Field(default=3, ge=1, le=10)
    enabled: bool = True

class ServiceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    host: str | None = Field(default=None, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    url: str | None = Field(default=None, max_length=500)
    expect_status: str | None = Field(default=None, max_length=50)
    expect_text: str | None = Field(default=None, max_length=200)
    verify_tls: bool | None = None
    dns_query: str | None = Field(default=None, max_length=255)
    dns_type: DnsType | None = None
    dns_expect: str | None = Field(default=None, max_length=255)
    interval_s: int | None = Field(default=None, ge=10, le=3600)
    timeout_s: int | None = Field(default=None, ge=1, le=30)
    fail_threshold: int | None = Field(default=None, ge=1, le=10)
    enabled: bool | None = None

class ServiceOut(BaseModel):
    id: int
    device_id: int
    device_name: str
    name: str
    kind: str
    host: str | None
    port: int | None
    url: str | None
    expect_status: str | None
    expect_text: str | None
    verify_tls: bool
    dns_query: str | None
    dns_type: str
    dns_expect: str | None
    interval_s: int
    timeout_s: int
    fail_threshold: int
    enabled: bool
    state: str
    consecutive_failures: int
    last_check_at: datetime | None
    last_latency_ms: float | None
    last_change_at: datetime | None
    last_error: str | None

class ResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    checked_at: datetime
    success: bool
    latency_ms: float | None
    error: str | None

def _validate(c) -> None:
    """Valida la configuración (sirve para el esquema de entrada y para el objeto de la base)."""
    try:
        if c.host:
            validate_host(c.host)
        if c.kind == "tcp":
            if not c.port:
                raise CheckConfigError("Las comprobaciones TCP necesitan un puerto")
        elif c.kind == "http":
            if not c.url:
                raise CheckConfigError("Las comprobaciones HTTP necesitan una URL")
            validate_http_url(c.url)
            parse_status_ranges(c.expect_status)
        elif c.kind == "dns":
            if not c.dns_query:
                raise CheckConfigError("Las comprobaciones DNS necesitan un nombre a consultar")
            validate_dns_name(c.dns_query)
            if c.host:
                try:
                    ipaddress.ip_address(c.host)
                except ValueError:
                    raise CheckConfigError("El servidor DNS debe ser una dirección IP")
    except CheckConfigError as e:
        raise HTTPException(422, str(e))
    if c.timeout_s >= c.interval_s:
        raise HTTPException(422, "El timeout debe ser menor que el intervalo")

def _out(c: ServiceCheck, device_name: str, st: ServiceStatus | None) -> ServiceOut:
    return ServiceOut(
        id=c.id, device_id=c.device_id, device_name=device_name, name=c.name, kind=c.kind,
        host=c.host, port=c.port, url=c.url, expect_status=c.expect_status,
        expect_text=c.expect_text, verify_tls=c.verify_tls, dns_query=c.dns_query,
        dns_type=c.dns_type, dns_expect=c.dns_expect, interval_s=c.interval_s,
        timeout_s=c.timeout_s, fail_threshold=c.fail_threshold, enabled=c.enabled,
        state=st.state if st else "UNKNOWN",
        consecutive_failures=st.consecutive_failures if st else 0,
        last_check_at=st.last_check_at if st else None,
        last_latency_ms=st.last_latency_ms if st else None,
        last_change_at=st.last_change_at if st else None,
        last_error=st.last_error if st else None)

def _get(db: Session, check_id: int) -> ServiceCheck:
    c = db.get(ServiceCheck, check_id)
    if not c:
        raise HTTPException(404, "Comprobación no encontrada")
    return c

@router.get("", response_model=list[ServiceOut])
def list_services(device_id: int | None = None, db: Session = Depends(get_db)):
    q = (select(ServiceCheck, Device.name, ServiceStatus)
         .join(Device, Device.id == ServiceCheck.device_id)
         .outerjoin(ServiceStatus, ServiceStatus.check_id == ServiceCheck.id)
         .order_by(Device.name, ServiceCheck.name))
    if device_id is not None:
        q = q.where(ServiceCheck.device_id == device_id)
    return [_out(c, name, st) for c, name, st in db.execute(q).all()]

@router.post("", response_model=ServiceOut, status_code=201)
def create_service(payload: ServiceCreate, db: Session = Depends(get_db)):
    dev = db.get(Device, payload.device_id)
    if not dev:
        raise HTTPException(404, "El dispositivo no existe")
    _validate(payload)
    c = ServiceCheck(**payload.model_dump())
    db.add(c)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ese dispositivo ya tiene una comprobación con ese nombre")
    db.refresh(c)
    return _out(c, dev.name, None)

@router.patch("/{check_id}", response_model=ServiceOut)
def update_service(check_id: int, payload: ServiceUpdate, db: Session = Depends(get_db)):
    c = _get(db, check_id)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(c, k, v)
    _validate(c)          # si falla, la sesión se descarta sin guardar
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ese dispositivo ya tiene una comprobación con ese nombre")
    db.refresh(c)
    return _out(c, db.get(Device, c.device_id).name, db.get(ServiceStatus, c.id))

@router.delete("/{check_id}", status_code=204, response_class=Response)
def delete_service(check_id: int, db: Session = Depends(get_db)):
    db.delete(_get(db, check_id))    # el estado y el histórico se eliminan en cascada
    db.commit()
    return Response(status_code=204)

@router.post("/{check_id}/recheck", status_code=204, response_class=Response)
def recheck(check_id: int, db: Session = Depends(get_db)):
    """No sondea: marca la comprobación como pendiente y la ejecuta el worker en su siguiente ciclo."""
    _get(db, check_id)
    st = db.get(ServiceStatus, check_id)
    if st:
        st.last_check_at = None
        db.commit()
    return Response(status_code=204)

@router.get("/{check_id}/results", response_model=list[ResultOut])
def results(check_id: int, minutes: int = Query(60, ge=1, le=10080), db: Session = Depends(get_db)):
    _get(db, check_id)
    since = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    return db.scalars(select(ServiceResult)
                      .where(ServiceResult.check_id == check_id, ServiceResult.checked_at >= since)
                      .order_by(ServiceResult.checked_at)).all()
