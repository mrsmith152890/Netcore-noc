import asyncio
import base64
import binascii
import ipaddress
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, IPvAnyAddress, field_validator, model_validator
from sqlalchemy import and_, delete, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import decrypt
from app.models import Device, DiscoveryScope, MapDomain, MapDomainMap, MapLink, MapNode, NetworkMap, SnmpCredential, SnmpIdentity
from app.modules.discovery.scope import ScopeError, host_list, validate_cidr
from app.modules.maps.hierarchy import descendants, would_create_cycle
from app.modules.monitoring.probe import ping
from app.modules.monitoring.snmp import SnmpError, snmp_get, snmp_walk

router = APIRouter(prefix="/maps", tags=["maps"])

# ---------- esquemas ----------
class MapCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=255)
    domain_ids: list[int] = Field(default_factory=list, max_length=100)
    domain_id: int | None = None  # compatibilidad con clientes anteriores

class MapUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=255)
    domain_ids: list[int] | None = Field(default=None, max_length=100)
    domain_id: int | None = None  # compatibilidad con clientes anteriores

class MapScanIn(BaseModel):
    router_device_id: int
    cidr: str = Field(min_length=7, max_length=50)

class MapScanHost(BaseModel):
    ip: str
    source: Literal["ping"] = "ping"
    rtt_ms: float | None = None
    label: str | None = Field(default=None, max_length=200)

class MapScanOut(BaseModel):
    router_device_id: int
    router_name: str
    cidr: str
    arp_available: bool
    arp_error: str | None
    hosts: list[MapScanHost]

class MapFromScanIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=255)
    domain_ids: list[int] = Field(default_factory=list, max_length=100)
    domain_id: int | None = None  # compatibilidad con clientes anteriores
    router_device_id: int
    cidr: str = Field(min_length=7, max_length=50)
    hosts: list[MapScanHost] = Field(default_factory=list, max_length=256)

class MapOut(BaseModel):
    id: int
    name: str
    description: str | None
    domain_ids: list[int]
    domain_names: list[str]
    domain_id: int | None = None
    domain_name: str | None = None
    created_at: datetime

class MapDomainCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)

class MapDomainOut(BaseModel):
    id: int
    name: str

class AutoConnectOut(BaseModel):
    anchor_node_id: int
    created: int

class NodeCreate(BaseModel):
    device_id: int | None = None
    label: str | None = Field(default=None, max_length=200)
    child_map_id: int | None = None
    ip_address: IPvAnyAddress | None = None
    x: float = 0
    y: float = 0

    @model_validator(mode="after")
    def _exactly_one(self):
        if self.ip_address is not None:
            if self.device_id is not None or self.child_map_id is not None:
                raise ValueError("Una IP no se puede combinar con un dispositivo o submapa")
        else:
            given = [self.device_id is not None, bool(self.label), self.child_map_id is not None]
            if sum(given) != 1:
                raise ValueError("Indica un dispositivo, etiqueta, submapa o IP")
        return self

class NodeUpdate(BaseModel):
    label: str | None = Field(default=None, max_length=200)
    icon_data: str | None = Field(default=None, max_length=720000)

    @field_validator("icon_data")
    @classmethod
    def validate_icon_data(cls, value: str | None) -> str | None:
        if value is None:
            return None
        match = re.fullmatch(r"data:image/(png|jpeg|webp|svg\+xml);base64,([A-Za-z0-9+/]*={0,2})", value)
        if not match:
            raise ValueError("El icono debe ser PNG, JPEG, WebP o SVG en base64")
        mime, encoded = match.groups()
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("El archivo de icono no es base64 válido") from exc
        if not raw or len(raw) > 512 * 1024:
            raise ValueError("La imagen debe pesar como máximo 512 KB")
        if mime == "png" and not raw.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("El archivo no es un PNG válido")
        if mime == "jpeg" and not raw.startswith(b"\xff\xd8\xff"):
            raise ValueError("El archivo no es un JPEG válido")
        if mime == "webp" and (raw[:4] != b"RIFF" or raw[8:12] != b"WEBP"):
            raise ValueError("El archivo no es un WebP válido")
        if mime == "svg+xml":
            try:
                text = raw.decode("utf-8")
                if re.search(r"<!\s*(DOCTYPE|ENTITY)", text, re.IGNORECASE):
                    raise ValueError("El SVG no puede contener entidades ni DTD")
                root = ET.fromstring(text)
            except (UnicodeDecodeError, ET.ParseError) as exc:
                raise ValueError("El SVG no es válido") from exc
            if root.tag.rsplit("}", 1)[-1].lower() != "svg":
                raise ValueError("El archivo no contiene un elemento SVG")
            forbidden = {"script", "foreignobject", "iframe", "object", "embed", "audio", "video"}
            for element in root.iter():
                if element.tag.rsplit("}", 1)[-1].lower() in forbidden:
                    raise ValueError("El SVG contiene elementos activos no permitidos")
                for key, attr in element.attrib.items():
                    attr_name = key.rsplit("}", 1)[-1].lower()
                    val = attr.strip().lower()
                    if attr_name.startswith("on") or attr_name in {"href", "src"} and val and not val.startswith("#"):
                        raise ValueError("El SVG contiene referencias o eventos no permitidos")
                    if "javascript:" in val or "@import" in val or re.search(r"url\(\s*['\"]?(?!#)", val):
                        raise ValueError("El SVG contiene contenido externo no permitido")
            safe = ET.tostring(root, encoding="utf-8", xml_declaration=False)
            encoded = base64.b64encode(safe).decode("ascii")
            return "data:image/svg+xml;base64," + encoded
        return value

class NodeProbeOut(BaseModel):
    node_id: int
    ip_address: str
    ping_ok: bool
    rtt_ms: float | None
    snmp_checked: bool
    snmp_ok: bool | None
    state: Literal["SNMP", "UP", "DOWN"]
    checked_at: datetime

class NodeOut(BaseModel):
    id: int
    node_type: str
    device_id: int | None
    label: str | None
    x: float
    y: float
    device_name: str | None = None
    device_ip: str | None = None
    device_type: str | None = None
    device_enabled: bool | None = None
    ip_address: str | None = None
    discovery_source: str | None = None
    last_ping_ok: bool | None = None
    last_snmp_ok: bool | None = None
    last_arp_seen: bool | None = None
    last_checked_at: datetime | None = None
    icon_data: str | None = None
    device_snmp_ok: bool = False
    device_snmp_checked_at: datetime | None = None
    child_map_id: int | None = None
    child_map_name: str | None = None
    child_device_ids: list[int] = []

class LinkCreate(BaseModel):
    source_node_id: int
    target_node_id: int
    source_handle: str | None = Field(default=None, pattern=r"^[trbl]$")
    target_handle: str | None = Field(default=None, pattern=r"^[trbl]$")
    label: str | None = Field(default=None, max_length=100)

class LinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    source_node_id: int
    target_node_id: int
    source_handle: str | None
    target_handle: str | None
    label: str | None

class MapDetail(MapOut):
    nodes: list[NodeOut]
    links: list[LinkOut]

class Position(BaseModel):
    node_id: int
    x: float
    y: float

class LayoutIn(BaseModel):
    positions: list[Position]

# ---------- utilidades ----------
def _get_map(db: Session, map_id: int) -> NetworkMap:
    m = db.get(NetworkMap, map_id)
    if not m:
        raise HTTPException(404, "Mapa no encontrado")
    return m

def _edges(db: Session) -> dict[int, set[int]]:
    """Jerarquía actual: mapa padre -> mapas que contiene como submapas."""
    edges: dict[int, set[int]] = {}
    for parent, child in db.execute(
            select(MapNode.map_id, MapNode.child_map_id).where(MapNode.child_map_id.is_not(None))):
        edges.setdefault(parent, set()).add(child)
    return edges

def _devices_under(db: Session, edges: dict[int, set[int]], map_id: int) -> list[int]:
    """Dispositivos de un mapa y de todos sus submapas (para el estado agregado)."""
    ids = {map_id} | descendants(edges, map_id)
    return sorted(set(db.scalars(select(MapNode.device_id).where(
        MapNode.map_id.in_(ids), MapNode.device_id.is_not(None)))))

def _node_out(n: MapNode, d: Device | None, child_name: str | None = None,
              child_devices: list[int] | None = None, device_snmp_ok: bool = False,
              device_snmp_checked_at: datetime | None = None) -> NodeOut:
    return NodeOut(
        id=n.id, node_type=n.node_type, device_id=n.device_id, label=n.label, x=n.x, y=n.y,
        device_name=d.name if d else None, device_ip=d.ip_address if d else None,
        device_type=d.device_type if d else None, device_enabled=d.enabled if d else None,
        ip_address=n.ip_address, discovery_source=n.discovery_source,
        last_ping_ok=n.last_ping_ok, last_snmp_ok=n.last_snmp_ok,
        last_arp_seen=n.last_arp_seen, last_checked_at=n.last_checked_at,
        icon_data=n.icon_data,
        device_snmp_ok=device_snmp_ok, device_snmp_checked_at=device_snmp_checked_at,
        child_map_id=n.child_map_id, child_map_name=child_name,
        child_device_ids=child_devices or [])

def _get_node(db: Session, map_id: int, node_id: int) -> MapNode:
    n = db.get(MapNode, node_id)
    if not n or n.map_id != map_id:
        raise HTTPException(404, "Nodo no encontrado en este mapa")
    return n

# ---------- dominios de mapas ----------
def _map_out(db: Session, m: NetworkMap) -> MapOut:
    assigned = db.execute(
        select(MapDomainMap.domain_id, MapDomain.name)
        .join(MapDomain, MapDomain.id == MapDomainMap.domain_id)
        .where(MapDomainMap.map_id == m.id).order_by(MapDomain.name)
    ).all()
    domain_ids = [row[0] for row in assigned]
    domain_names = [row[1] for row in assigned]
    return MapOut(id=m.id, name=m.name, description=m.description,
                  domain_ids=domain_ids, domain_names=domain_names,
                  domain_id=domain_ids[0] if domain_ids else None,
                  domain_name=domain_names[0] if domain_names else None,
                  created_at=m.created_at)

def _validate_domains(db: Session, domain_ids: list[int]) -> list[int]:
    unique = list(dict.fromkeys(domain_ids))
    existing = set(db.scalars(select(MapDomain.id).where(MapDomain.id.in_(unique))).all()) if unique else set()
    missing = [domain_id for domain_id in unique if domain_id not in existing]
    if missing:
        raise HTTPException(404, "Dominio no encontrado: " + ", ".join(map(str, missing)))
    return unique

def _payload_domains(payload) -> list[int]:
    fields = payload.model_fields_set
    if "domain_ids" in fields:
        return payload.domain_ids or []
    if "domain_id" in fields and payload.domain_id is not None:
        return [payload.domain_id]
    return []

def _set_map_domains(db: Session, map_id: int, domain_ids: list[int]) -> None:
    db.execute(delete(MapDomainMap).where(MapDomainMap.map_id == map_id))
    for domain_id in domain_ids:
        db.add(MapDomainMap(map_id=map_id, domain_id=domain_id))

@router.get("/domains", response_model=list[MapDomainOut])
def list_map_domains(db: Session = Depends(get_db)):
    domains = db.scalars(select(MapDomain).order_by(MapDomain.name)).all()
    return [MapDomainOut(id=domain.id, name=domain.name) for domain in domains]

@router.post("/domains", response_model=MapDomainOut, status_code=201)
def create_map_domain(payload: MapDomainCreate, db: Session = Depends(get_db)):
    domain = MapDomain(name=payload.name.strip())
    db.add(domain)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ya existe ese dominio")
    db.refresh(domain)
    return MapDomainOut(id=domain.id, name=domain.name)

@router.delete("/domains/{domain_id}", status_code=204, response_class=Response)
def delete_map_domain(domain_id: int, db: Session = Depends(get_db)):
    domain = db.get(MapDomain, domain_id)
    if domain is None:
        raise HTTPException(404, "Dominio no encontrado")
    db.delete(domain)
    db.commit()
    return Response(status_code=204)

# ---------- mapas ----------
@router.post("", response_model=MapOut, status_code=201)
def create_map(payload: MapCreate, db: Session = Depends(get_db)):
    domain_ids = _validate_domains(db, _payload_domains(payload))
    m = NetworkMap(name=payload.name.strip(), description=payload.description)
    db.add(m)
    try:
        db.flush()
        _set_map_domains(db, m.id, domain_ids)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ya existe un mapa con ese nombre")
    db.refresh(m)
    return _map_out(db, m)

@router.get("", response_model=list[MapOut])
def list_maps(db: Session = Depends(get_db)):
    return [_map_out(db, m) for m in db.scalars(select(NetworkMap).order_by(NetworkMap.name))]

def _scan_network(cidr: str, router_ip: str, db: Session, site_id: int):
    try:
        raw = ipaddress.ip_network(cidr.strip(), strict=False)
        if raw.version != 4:
            raise ScopeError("Por ahora solo se admiten rangos IPv4")

        # Los mapas reutilizan la autorización por sitio del módulo Descubrimiento.
        # Solo se permite el CIDR registrado o una subred contenida dentro de él.
        allow_public = settings.discovery_allow_public
        if not raw.is_private and not allow_public:
            scopes = db.scalars(select(DiscoveryScope).where(
                DiscoveryScope.site_id == site_id,
                DiscoveryScope.enabled.is_(True),
                DiscoveryScope.allow_public.is_(True),
            )).all()
            for scope in scopes:
                try:
                    authorized_network = ipaddress.ip_network(scope.cidr, strict=True)
                except ValueError:
                    continue
                if raw.subnet_of(authorized_network):
                    allow_public = True
                    break

        network = validate_cidr(str(raw), allow_public=allow_public)
    except (ValueError, ScopeError) as e:
        raise HTTPException(400, str(e))
    address = ipaddress.ip_address(router_ip)
    if address.version != 4 or address not in network:
        raise HTTPException(400, "La subred IPv4 debe contener la IP del router")
    if network.num_addresses > 256:
        raise HTTPException(400, "El mapa permite escanear hasta 256 direcciones por solicitud")
    return network

def _arp_hosts(data: dict[str, str], network) -> set[str]:
    prefix = ".1.3.6.1.2.1.4.22.1.2."
    found: set[str] = set()
    for oid in data:
        if not oid.startswith(prefix):
            continue
        parts = oid[len(prefix):].split(".")
        if len(parts) != 5 or not all(part.isdigit() for part in parts):
            continue
        try:
            ip = ipaddress.IPv4Address(".".join(parts[1:]))
        except ipaddress.AddressValueError:
            continue
        if ip in network:
            found.add(str(ip))
    return found

@router.post("/discover", response_model=MapScanOut)
async def discover_map_hosts(payload: MapScanIn, db: Session = Depends(get_db)):
    router = db.get(Device, payload.router_device_id)
    if not router or not router.enabled:
        raise HTTPException(404, "Router habilitado no encontrado")
    network = _scan_network(payload.cidr, router.ip_address, db, router.site_id)

    targets = host_list(network)
    sem = asyncio.Semaphore(64)

    async def probe_one(ip: str):
        async with sem:
            try:
                return ip, await ping(ip, count=1, timeout_s=1)
            except Exception:
                return ip, None

    credential = db.get(SnmpCredential, router.id)
    arp_available = False
    arp_error: str | None = None
    arp_hosts: set[str] = set()
    arp_task = None
    if credential and credential.enabled:
        community = decrypt(credential.community_enc)
        arp_task = asyncio.create_task(
            snmp_walk(router.ip_address, credential.port, community, ".1.3.6.1.2.1.4.22.1.2"))
    else:
        arp_error = "SNMP no esta configurado o habilitado para este router"

    ping_results = await asyncio.gather(*(probe_one(ip) for ip in targets))
    ping_hosts = {ip for ip, result in ping_results if result and result.success}
    rtts = {ip: result.rtt_ms for ip, result in ping_results if result and result.success}

    if arp_task:
        try:
            arp_hosts = _arp_hosts(await arp_task, network)
            arp_available = True
        except (SnmpError, asyncio.TimeoutError) as e:
            arp_error = f"No se pudo leer la tabla ARP por SNMP: {str(e)[:180]}"

    # ARP queda como dato diagnóstico, pero no autoriza ni agrega hosts que no respondieron ping.
    hosts = [
        MapScanHost(ip=ip, source="ping", rtt_ms=rtts.get(ip))
        for ip in sorted(ping_hosts, key=ipaddress.ip_address)
    ]
    return MapScanOut(router_device_id=router.id, router_name=router.name, cidr=str(network),
                      arp_available=arp_available, arp_error=arp_error, hosts=hosts)

@router.post("/from-scan", response_model=MapOut, status_code=201)
def create_map_from_scan(payload: MapFromScanIn, db: Session = Depends(get_db)):
    router = db.get(Device, payload.router_device_id)
    if not router or not router.enabled:
        raise HTTPException(404, "Router o dispositivo de borde habilitado no encontrado")
    network = _scan_network(payload.cidr, router.ip_address, db, router.site_id)
    domain_ids = _validate_domains(db, _payload_domains(payload))
    checked: dict[str, MapScanHost] = {}
    for host in payload.hosts:
        try:
            ip = ipaddress.ip_address(host.ip)
        except ValueError:
            raise HTTPException(400, f"IP invalida: {host.ip}")
        if ip.version != 4 or ip not in network:
            raise HTTPException(400, f"La IP {host.ip} esta fuera de la subred {network}")
        if str(ip) != router.ip_address:
            checked[str(ip)] = host

    m = NetworkMap(name=payload.name.strip(), description=payload.description)
    checked_at = datetime.now(timezone.utc)
    known_devices = {}
    if checked:
        known_devices = {d.ip_address: d for d in db.scalars(
            select(Device).where(Device.site_id == router.site_id,
                                 Device.ip_address.in_(list(checked))))}
    db.add(m)
    try:
        db.flush()
        _set_map_domains(db, m.id, domain_ids)
        router_node = MapNode(map_id=m.id, node_type="device", device_id=router.id, x=80, y=180)
        db.add(router_node)
        db.flush()
        for index, (ip, host) in enumerate(sorted(checked.items(), key=lambda row: ipaddress.ip_address(row[0]))):
            x, y = 300 + (index % 4) * 190, 60 + (index // 4) * 135
            device = known_devices.get(ip)
            node = (MapNode(map_id=m.id, node_type="device", device_id=device.id, label=host.label, x=x, y=y)
                    if device else MapNode(
                        map_id=m.id, node_type="ip", ip_address=ip, discovery_source=host.source,
                        last_ping_ok=True, last_snmp_ok=None, last_arp_seen=False,
                        last_checked_at=checked_at, label=host.label, x=x, y=y))
            db.add(node)
            db.flush()
            db.add(MapLink(map_id=m.id, source_node_id=router_node.id, target_node_id=node.id))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ya existe un mapa con ese nombre")
    db.refresh(m)
    return _map_out(db, m)

@router.get("/{map_id}", response_model=MapDetail)
def get_map(map_id: int, db: Session = Depends(get_db)):
    m = _get_map(db, map_id)
    rows = db.execute(
        select(MapNode, Device).outerjoin(Device, Device.id == MapNode.device_id)
        .where(MapNode.map_id == map_id).order_by(MapNode.id)).all()
    child_ids = {n.child_map_id for n, _ in rows if n.child_map_id}
    device_ids = {n.device_id for n, _ in rows if n.device_id}
    names: dict[int, str] = {}
    edges: dict[int, set[int]] = {}
    if child_ids:
        names = {c.id: c.name for c in db.scalars(select(NetworkMap).where(NetworkMap.id.in_(child_ids)))}
        edges = _edges(db)
    credentials = {c.device_id: c for c in db.scalars(
        select(SnmpCredential).where(SnmpCredential.device_id.in_(device_ids)))} if device_ids else {}
    identities = {i.device_id: i for i in db.scalars(
        select(SnmpIdentity).where(SnmpIdentity.device_id.in_(device_ids)))} if device_ids else {}
    now = datetime.now(timezone.utc)

    def snmp_state(device_id: int | None):
        credential = credentials.get(device_id) if device_id else None
        identity = identities.get(device_id) if device_id else None
        checked_at = identity.last_poll_at if identity else None
        fresh = bool(checked_at and now - checked_at <= timedelta(seconds=max(settings.snmp_interval_s * 3, 180)))
        ok = bool(credential and credential.enabled and identity and fresh and
                  identity.last_success_at and not identity.last_error)
        return ok, checked_at

    nodes = []
    for n, d in rows:
        snmp_ok, snmp_checked_at = snmp_state(n.device_id)
        nodes.append(_node_out(
            n, d, names.get(n.child_map_id) if n.child_map_id else None,
            _devices_under(db, edges, n.child_map_id) if n.child_map_id else None,
            device_snmp_ok=snmp_ok, device_snmp_checked_at=snmp_checked_at))
    links = db.scalars(select(MapLink).where(MapLink.map_id == map_id).order_by(MapLink.id)).all()
    return MapDetail(**_map_out(db, m).model_dump(),
                     nodes=nodes, links=[LinkOut.model_validate(l) for l in links])

@router.patch("/{map_id}", response_model=MapOut)
def update_map(map_id: int, payload: MapUpdate, db: Session = Depends(get_db)):
    m = _get_map(db, map_id)
    changes = payload.model_dump(exclude_unset=True)
    domain_ids = None
    if "domain_ids" in changes or "domain_id" in changes:
        domain_ids = _validate_domains(db, _payload_domains(payload))
    for key, value in changes.items():
        if key not in ("domain_ids", "domain_id"):
            setattr(m, key, value)
    try:
        if domain_ids is not None:
            _set_map_domains(db, m.id, domain_ids)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ya existe un mapa con ese nombre")
    db.refresh(m)
    return _map_out(db, m)

@router.delete("/{map_id}", status_code=204, response_class=Response)
def delete_map(map_id: int, db: Session = Depends(get_db)):
    """Borra el mapa y, en cascada, sus nodos y enlaces, y los nodos de submapa que lo
    referencian en otros mapas. Los dispositivos no se tocan."""
    db.delete(_get_map(db, map_id))
    db.commit()
    return Response(status_code=204)

@router.post("/{map_id}/auto-connect", response_model=AutoConnectOut)
def auto_connect_map(map_id: int, db: Session = Depends(get_db)):
    _get_map(db, map_id)
    anchor = db.execute(
        select(MapNode, Device).join(Device, Device.id == MapNode.device_id)
        .where(MapNode.map_id == map_id, MapNode.node_type == "device",
               Device.device_type.in_(("router", "firewall")))
        .order_by(MapNode.id).limit(1)).first()
    if anchor is None:
        raise HTTPException(409, "Agrega primero al mapa un router o firewall para enlazar los equipos")
    root, _device = anchor
    nodes = db.scalars(select(MapNode).where(
        MapNode.map_id == map_id, MapNode.node_type.in_(("device", "ip")),
        MapNode.id != root.id).order_by(MapNode.id)).all()
    existing = {(min(l.source_node_id, l.target_node_id), max(l.source_node_id, l.target_node_id))
                for l in db.scalars(select(MapLink).where(MapLink.map_id == map_id))}
    created = 0
    for node in nodes:
        key = (min(root.id, node.id), max(root.id, node.id))
        if key in existing:
            continue
        db.add(MapLink(map_id=map_id, source_node_id=root.id, target_node_id=node.id))
        existing.add(key)
        created += 1
    db.commit()
    return AutoConnectOut(anchor_node_id=root.id, created=created)

# ---------- nodos ----------
@router.post("/{map_id}/nodes", response_model=NodeOut, status_code=201)
def add_node(map_id: int, payload: NodeCreate, db: Session = Depends(get_db)):
    _get_map(db, map_id)
    device = child = None
    if payload.device_id is not None:
        device = db.get(Device, payload.device_id)
        if not device:
            raise HTTPException(404, "El dispositivo no existe")
    elif payload.child_map_id is not None:
        child = db.get(NetworkMap, payload.child_map_id)
        if not child:
            raise HTTPException(404, "El mapa indicado no existe")
        if would_create_cycle(_edges(db), map_id, child.id):
            raise HTTPException(409, "Un mapa no puede contenerse a sí mismo, ni directa ni indirectamente")
    ip = str(payload.ip_address) if payload.ip_address is not None else None
    node = MapNode(map_id=map_id, node_type="device" if device else "map" if child else "ip" if ip else "label",
                   device_id=payload.device_id, child_map_id=payload.child_map_id,
                   ip_address=ip, discovery_source="manual" if ip else None,
                   label=payload.label, x=payload.x, y=payload.y)
    db.add(node)
    try:
        db.flush()
        if node.node_type in ("device", "ip"):
            anchor = db.execute(
                select(MapNode, Device).join(Device, Device.id == MapNode.device_id)
                .where(MapNode.map_id == map_id, MapNode.node_type == "device",
                       Device.device_type.in_(("router", "firewall")))
                .order_by(MapNode.id).limit(1)).first()
            if anchor and anchor[0].id != node.id:
                root = anchor[0]
                pair = (min(root.id, node.id), max(root.id, node.id))
                links = db.scalars(select(MapLink).where(MapLink.map_id == map_id)).all()
                if not any((min(link.source_node_id, link.target_node_id),
                            max(link.source_node_id, link.target_node_id)) == pair for link in links):
                    db.add(MapLink(map_id=map_id, source_node_id=root.id, target_node_id=node.id))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ese dispositivo o submapa ya está en este mapa")
    db.refresh(node)
    return _node_out(node, device, child.name if child else None,
                     _devices_under(db, _edges(db), child.id) if child else None)

@router.post("/{map_id}/nodes/{node_id}/ping", response_model=NodeProbeOut)
async def ping_map_node(map_id: int, node_id: int, db: Session = Depends(get_db)):
    node = _get_node(db, map_id, node_id)
    device = db.get(Device, node.device_id) if node.device_id else None
    ip = device.ip_address if device else node.ip_address
    if not ip:
        raise HTTPException(400, "Selecciona un nodo de dispositivo o IP")

    credential = db.get(SnmpCredential, device.id) if device else None
    if credential is None:
        credential = db.scalar(
            select(SnmpCredential).join(Device, Device.id == SnmpCredential.device_id)
            .where(Device.ip_address == ip, Device.enabled.is_(True), SnmpCredential.enabled.is_(True))
            .order_by(Device.id).limit(1))
    if credential and not credential.enabled:
        credential = None
    community = decrypt(credential.community_enc) if credential else None

    ping_task = asyncio.create_task(ping(ip, count=1, timeout_s=1))
    snmp_task = asyncio.create_task(
        snmp_get(ip, credential.port, community, [".1.3.6.1.2.1.1.5.0"])
    ) if credential else None
    ping_result = None
    try:
        ping_result = await ping_task
    except Exception:
        pass
    snmp_ok = None
    if snmp_task:
        try:
            response = await snmp_task
            snmp_ok = bool(response)
        except Exception:
            snmp_ok = False

    checked_at = datetime.now(timezone.utc)
    ping_ok = bool(ping_result and ping_result.success)
    state = "SNMP" if snmp_ok else "UP" if ping_ok else "DOWN"
    node.last_ping_ok = ping_ok
    node.last_snmp_ok = snmp_ok
    node.last_arp_seen = False
    node.last_checked_at = checked_at
    db.commit()
    return NodeProbeOut(
        node_id=node.id, ip_address=ip, ping_ok=ping_ok,
        rtt_ms=ping_result.rtt_ms if ping_result and ping_result.success else None,
        snmp_checked=credential is not None, snmp_ok=snmp_ok, state=state, checked_at=checked_at)

@router.patch("/{map_id}/nodes/{node_id}", response_model=NodeOut)
def update_node(map_id: int, node_id: int, payload: NodeUpdate, db: Session = Depends(get_db)):
    node = _get_node(db, map_id, node_id)
    if node.node_type not in ("label", "ip", "device"):
        raise HTTPException(400, "Este nodo no admite edición de identidad")
    data = payload.model_dump(exclude_unset=True)
    if "label" in data:
        node.label = data["label"]
    if "icon_data" in data:
        node.icon_data = data["icon_data"]
    db.commit()
    db.refresh(node)
    return _node_out(node, None)

@router.delete("/{map_id}/nodes/{node_id}", status_code=204, response_class=Response)
def delete_node(map_id: int, node_id: int, db: Session = Depends(get_db)):
    db.delete(_get_node(db, map_id, node_id))   # borrar un nodo de submapa no borra el mapa hijo
    db.commit()
    return Response(status_code=204)

@router.put("/{map_id}/layout", status_code=204, response_class=Response)
def save_layout(map_id: int, payload: LayoutIn, db: Session = Depends(get_db)):
    _get_map(db, map_id)
    ids = [p.node_id for p in payload.positions]
    nodes = {n.id: n for n in db.scalars(
        select(MapNode).where(MapNode.map_id == map_id, MapNode.id.in_(ids)))}
    for p in payload.positions:
        n = nodes.get(p.node_id)
        if n:
            n.x, n.y = p.x, p.y
    db.commit()
    return Response(status_code=204)

# ---------- enlaces ----------
@router.post("/{map_id}/links", response_model=LinkOut, status_code=201)
def add_link(map_id: int, payload: LinkCreate, db: Session = Depends(get_db)):
    _get_map(db, map_id)
    s, t = payload.source_node_id, payload.target_node_id
    if s == t:
        raise HTTPException(400, "Un enlace necesita dos nodos distintos")
    found = set(db.scalars(select(MapNode.id).where(MapNode.map_id == map_id, MapNode.id.in_([s, t]))))
    if len(found) != 2:
        raise HTTPException(404, "Los dos nodos deben pertenecer a este mapa")
    exists = db.scalar(select(MapLink.id).where(
        MapLink.map_id == map_id,
        or_(and_(MapLink.source_node_id == s, MapLink.target_node_id == t),
            and_(MapLink.source_node_id == t, MapLink.target_node_id == s))))
    if exists:
        raise HTTPException(409, "Ya existe un enlace entre esos dos nodos")
    link = MapLink(map_id=map_id, **payload.model_dump())
    db.add(link)
    db.commit()
    db.refresh(link)
    return link

@router.delete("/{map_id}/links/{link_id}", status_code=204, response_class=Response)
def delete_link(map_id: int, link_id: int, db: Session = Depends(get_db)):
    link = db.get(MapLink, link_id)
    if not link or link.map_id != map_id:
        raise HTTPException(404, "Enlace no encontrado")
    db.delete(link)
    db.commit()
    return Response(status_code=204)
