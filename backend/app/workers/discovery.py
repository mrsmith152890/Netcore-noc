import asyncio
import ipaddress
import logging
import signal
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.heartbeat import beat
from app.core.logging import setup_logging
from app.core.security import decrypt
from app.models import Device, DiscoveredHost, DiscoveryRun, DiscoveryScope
from app.modules.discovery.classify import classify
from app.modules.discovery.scope import ScopeError, host_list, validate_cidr
from app.modules.monitoring.probe import ProbeResult, ping
from app.modules.monitoring.snmp import get_identity

log = logging.getLogger("netcore.discovery")
CHUNK = 64

def _now() -> datetime:
    return datetime.now(timezone.utc)

def _status(run_id: int) -> str | None:
    with SessionLocal() as db:
        return db.scalar(select(DiscoveryRun.status).where(DiscoveryRun.id == run_id))

def _fail(run_id: int, error: str) -> None:
    with SessionLocal() as db:
        run = db.get(DiscoveryRun, run_id)
        if run is None or run.status == "cancelled":
            return
        run.status, run.finished_at, run.error = "failed", _now(), error[:250]
        db.commit()

async def scan(run_id: int) -> None:
    with SessionLocal() as db:
        run = db.get(DiscoveryRun, run_id)
        scope = db.get(DiscoveryScope, run.scope_id)
        run.status, run.started_at = "running", _now()
        db.commit()
        cidr, site_id, port, allow_public = scope.cidr, scope.site_id, scope.snmp_port, scope.allow_public
        community = decrypt(scope.community_enc) if scope.community_enc else None
        known = {ip: dev_id for dev_id, ip in db.execute(
            select(Device.id, Device.ip_address).where(Device.site_id == site_id))}

    net = validate_cidr(cidr, allow_public=allow_public)   # defensa en profundidad: se vuelve a validar antes de escanear
    ips = host_list(net)
    with SessionLocal() as db:
        run = db.get(DiscoveryRun, run_id)
        run.hosts_total, run.hosts_scanned, run.hosts_alive = len(ips), 0, 0
        db.commit()
    log.info("Escaneo %s: %s (%d direcciones)", run_id, cidr, len(ips))

    # 1) barrido ICMP por bloques, comprobando cancelación entre bloques
    sem = asyncio.Semaphore(settings.discovery_concurrency)

    async def probe(ip: str):
        async with sem:
            return ip, await ping(ip, settings.discovery_ping_count, settings.ping_timeout_s)

    alive: dict[str, ProbeResult] = {}
    for i in range(0, len(ips), CHUNK):
        if _status(run_id) == "cancelled":
            log.info("Escaneo %s cancelado", run_id)
            return
        chunk = await asyncio.gather(*(probe(ip) for ip in ips[i:i + CHUNK]))
        for ip, r in chunk:
            if r.success:
                alive[ip] = r
        with SessionLocal() as db:
            run = db.get(DiscoveryRun, run_id)
            run.hosts_scanned = min(i + len(chunk), len(ips))
            run.hosts_alive = len(alive)
            db.commit()

    # 2) identificación SNMP de los que respondieron
    snmp: dict[str, dict] = {}
    if community and alive:
        sem2 = asyncio.Semaphore(settings.discovery_snmp_concurrency)

        async def identify(ip: str):
            async with sem2:
                try:
                    return ip, await get_identity(ip, port, community)
                except Exception:
                    return ip, None

        for ip, ident in await asyncio.gather(*(identify(ip) for ip in alive)):
            if ident and (ident.get("sys_name") or ident.get("sys_object_id")):
                snmp[ip] = ident

    if _status(run_id) == "cancelled":
        return

    # 3) guardar resultados
    with SessionLocal() as db:
        run = db.get(DiscoveryRun, run_id)
        for ip in sorted(alive, key=ipaddress.ip_address):
            ident = snmp.get(ip)
            vendor, dtype = classify(ident["sys_object_id"], ident["sys_descr"]) if ident else (None, "other")
            dev_id = known.get(ip)
            db.add(DiscoveredHost(
                run_id=run_id, ip=ip, rtt_ms=alive[ip].rtt_ms, snmp_ok=ident is not None,
                sys_name=ident["sys_name"] if ident else None,
                sys_descr=ident["sys_descr"] if ident else None,
                sys_object_id=ident["sys_object_id"] if ident else None,
                vendor=vendor, device_type=dtype, device_id=dev_id,
                status="registered" if dev_id else "new"))
        run.status, run.finished_at = "done", _now()
        run.hosts_total, run.hosts_alive, run.hosts_snmp = len(ips), len(alive), len(snmp)
        db.commit()
    log.info("Escaneo %s terminado: %d vivos, %d con SNMP", run_id, len(alive), len(snmp))

def _fail_interrupted() -> None:
    with SessionLocal() as db:
        for run in db.scalars(select(DiscoveryRun).where(DiscoveryRun.status == "running")):
            run.status, run.finished_at = "failed", _now()
            run.error = "Interrumpido por reinicio del worker"
        db.commit()

def _next_pending() -> int | None:
    with SessionLocal() as db:
        return db.scalar(select(DiscoveryRun.id).where(DiscoveryRun.status == "pending")
                         .order_by(DiscoveryRun.id).limit(1))

async def main() -> None:
    setup_logging()
    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    _fail_interrupted()
    log.info("Worker de descubrimiento iniciado")
    while not stop.is_set():
        try:
            run_id = _next_pending()
            await asyncio.to_thread(beat, "discovery", None, None)
        except Exception:      # base caída: el worker sigue vivo y reintenta
            log.exception("No se pudo consultar la cola de escaneos")
            run_id = None
        if run_id is not None:
            try:
                await scan(run_id)
            except ScopeError as e:
                _fail(run_id, str(e))
            except Exception as e:
                log.exception("Fallo en el escaneo %s", run_id)
                _fail(run_id, f"{type(e).__name__}: {e}")
            continue
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.discovery_poll_interval_s)
        except asyncio.TimeoutError:
            pass
    log.info("Worker de descubrimiento detenido")

if __name__ == "__main__":
    asyncio.run(main())
