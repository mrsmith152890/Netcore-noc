import asyncio
import logging
import signal
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.heartbeat import beat
from app.core.logging import setup_logging
from app.core.security import decrypt
from app.models import (Device, DeviceMetric, DeviceStatus, Interface, InterfaceSample, Site,
                        SnmpCredential, SnmpIdentity)
from app.modules.monitoring.rates import counter_rate_bps
from app.modules.monitoring.snmp import (InterfaceData, SnmpError, get_identity,
                                         get_interfaces, get_resources)

log = logging.getLogger("netcore.snmp")

async def _safe_resources(ip: str, port: int, community: str):
    try:
        return await get_resources(ip, port, community)
    except SnmpError as e:
        log.debug("Sin métricas de recursos en %s: %s", ip, e)
        return None

async def collect(ip: str, port: int, community: str):
    identity = await get_identity(ip, port, community)   # si falla, se omite el resto
    interfaces, resources = await asyncio.gather(
        get_interfaces(ip, port, community),
        _safe_resources(ip, port, community),
    )
    return identity, interfaces, resources

def store_interfaces(db: Session, dev_id: int, items: list[InterfaceData], now: datetime) -> None:
    existing = {i.if_index: i for i in db.scalars(select(Interface).where(Interface.device_id == dev_id))}
    prev: dict[int, InterfaceSample] = {}
    if existing:
        latest_samples = (
            select(
                InterfaceSample.interface_id,
                __import__("sqlalchemy").func.max(InterfaceSample.sampled_at).label("latest_at"),
            )
            .where(InterfaceSample.interface_id.in_([i.id for i in existing.values()]))
            .group_by(InterfaceSample.interface_id)
            .subquery()
        )
        q = (
            select(InterfaceSample)
            .join(
                latest_samples,
                (InterfaceSample.interface_id == latest_samples.c.interface_id)
                & (InterfaceSample.sampled_at == latest_samples.c.latest_at),
            )
        )
        prev = {s.interface_id: s for s in db.scalars(q)}

    for it in items:
        iface = existing.get(it.if_index)
        if iface is None:
            iface = Interface(device_id=dev_id, if_index=it.if_index, monitored=True)
            db.add(iface)
            db.flush()
        iface.name, iface.descr, iface.speed_bps = it.name, it.descr, it.speed_bps
        iface.admin_status, iface.oper_status, iface.last_seen_at = it.admin_status, it.oper_status, now

        if not iface.monitored:
            continue
        p = prev.get(iface.id)
        dt = (now - p.sampled_at).total_seconds() if p else 0.0
        db.add(InterfaceSample(
            interface_id=iface.id, sampled_at=now,
            in_octets=it.in_octets, out_octets=it.out_octets,
            in_bps=counter_rate_bps(p.in_octets if p else None, it.in_octets, dt, it.counter_bits),
            out_bps=counter_rate_bps(p.out_octets if p else None, it.out_octets, dt, it.counter_bits),
            oper_status=it.oper_status,
        ))

async def run_cycle() -> None:
    with SessionLocal() as db:
        rows = db.execute(
            select(Device.id, Device.ip_address, SnmpCredential.port, SnmpCredential.community_enc)
            .join(SnmpCredential, SnmpCredential.device_id == Device.id)
            .join(Site, Site.id == Device.site_id)
            .outerjoin(DeviceStatus, DeviceStatus.device_id == Device.id)
            .where(Device.enabled.is_(True), Site.enabled.is_(True), SnmpCredential.enabled.is_(True),
                   or_(DeviceStatus.state.is_(None), DeviceStatus.state != "DOWN"))
        ).all()
    targets = [(i, ip, port, decrypt(enc)) for i, ip, port, enc in rows]

    sem = asyncio.Semaphore(settings.snmp_concurrency)

    async def one(dev_id, ip, port, community):
        async with sem:
            try:
                return dev_id, await collect(ip, port, community), None
            except Exception as e:
                return dev_id, None, f"{type(e).__name__}: {e}"[:250]

    results = await asyncio.gather(*(one(*t) for t in targets))
    now = datetime.now(timezone.utc)

    with SessionLocal() as db:
        for dev_id, data, error in results:
            ident = db.get(SnmpIdentity, dev_id)
            if ident is None:
                ident = SnmpIdentity(device_id=dev_id)
                db.add(ident)
            ident.last_poll_at = now
            if error:
                ident.last_error = error
                log.warning("SNMP dispositivo %s: %s", dev_id, error)
                continue
            identity, interfaces, resources = data
            ident.last_error = None
            ident.last_success_at = now
            ident.sys_name = identity["sys_name"]
            ident.sys_descr = identity["sys_descr"]
            ident.sys_object_id = identity["sys_object_id"]
            ident.uptime_s = identity["uptime_s"]
            store_interfaces(db, dev_id, interfaces, now)
            if resources is not None:
                db.add(DeviceMetric(device_id=dev_id, sampled_at=now, cpu_pct=resources.cpu_pct,
                                    mem_total=resources.mem_total, mem_used=resources.mem_used,
                                    mem_pct=resources.mem_pct))
        db.commit()
    log.info("Ciclo SNMP completo: %d dispositivos", len(results))

async def main() -> None:
    setup_logging()
    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    log.info("Poller SNMP iniciado (intervalo %ss)", settings.snmp_interval_s)
    while not stop.is_set():
        started = loop.time()
        try:
            await run_cycle()
            await asyncio.to_thread(beat, "snmp", None, int((loop.time() - started) * 1000))
        except Exception:
            log.exception("Fallo en el ciclo SNMP")
        wait = max(0.0, settings.snmp_interval_s - (loop.time() - started))
        try:
            await asyncio.wait_for(stop.wait(), timeout=wait)
        except asyncio.TimeoutError:
            pass
    log.info("Poller SNMP detenido")

if __name__ == "__main__":
    asyncio.run(main())
