import asyncio
import ipaddress
import logging
import signal
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.heartbeat import beat
from app.core.logging import setup_logging
from app.models import Device, ServiceCheck, ServiceResult, ServiceStatus, Site
from app.modules.monitoring.state import apply_result
from app.modules.services.checks import (CheckConfigError, CheckResult, parse_status_ranges, run_dns,
                                         run_http, run_tcp, validate_host, validate_http_url)

log = logging.getLogger("netcore.services")

@dataclass
class Spec:
    id: int
    kind: str
    ip: str
    host: str | None
    port: int | None
    url: str | None
    expect_status: str | None
    expect_text: str | None
    verify_tls: bool
    dns_query: str | None
    dns_type: str
    dns_expect: str | None
    timeout_s: int
    fail_threshold: int

async def execute(spec: Spec) -> CheckResult:
    try:
        if spec.kind == "tcp":
            return await run_tcp(validate_host(spec.host or spec.ip), spec.port or 0, spec.timeout_s)
        if spec.kind == "http":
            ip = f"[{spec.ip}]" if ":" in spec.ip else spec.ip
            url = validate_http_url((spec.url or "").replace("{ip}", ip))   # se revalida con la IP real
            return await run_http(url, parse_status_ranges(spec.expect_status), spec.expect_text,
                                  spec.verify_tls, spec.timeout_s)
        if spec.kind == "dns":
            server = validate_host(spec.host or spec.ip)
            try:
                ipaddress.ip_address(server)
            except ValueError:
                raise CheckConfigError("El servidor DNS debe ser una dirección IP")
            return await run_dns(server, spec.port or 53, spec.dns_query or "", spec.dns_type,
                                 spec.dns_expect, spec.timeout_s)
        return CheckResult(False, None, f"Tipo desconocido: {spec.kind}")
    except CheckConfigError as e:
        return CheckResult(False, None, f"Configuración inválida: {e}")
    except Exception as e:
        return CheckResult(False, None, f"{type(e).__name__}: {e}"[:200])

async def run_due() -> int:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        rows = db.execute(
            select(ServiceCheck, Device.ip_address, ServiceStatus.last_check_at)
            .join(Device, Device.id == ServiceCheck.device_id)
            .join(Site, Site.id == Device.site_id)
            .outerjoin(ServiceStatus, ServiceStatus.check_id == ServiceCheck.id)
            .where(ServiceCheck.enabled.is_(True), Device.enabled.is_(True), Site.enabled.is_(True))).all()
        specs = [
            Spec(id=c.id, kind=c.kind, ip=ip, host=c.host, port=c.port, url=c.url,
                 expect_status=c.expect_status, expect_text=c.expect_text, verify_tls=c.verify_tls,
                 dns_query=c.dns_query, dns_type=c.dns_type, dns_expect=c.dns_expect,
                 timeout_s=c.timeout_s, fail_threshold=c.fail_threshold)
            for c, ip, last in rows
            if last is None or (now - last).total_seconds() >= c.interval_s]
    if not specs:
        return 0

    sem = asyncio.Semaphore(settings.service_concurrency)

    async def one(spec: Spec):
        async with sem:
            return spec, await execute(spec)

    results = await asyncio.gather(*(one(s) for s in specs))
    done = datetime.now(timezone.utc)

    with SessionLocal() as db:
        for spec, res in results:
            if db.get(ServiceCheck, spec.id) is None:    # se borró mientras se ejecutaba
                continue
            st = db.get(ServiceStatus, spec.id)
            if st is None:
                st = ServiceStatus(check_id=spec.id, state="UNKNOWN", consecutive_failures=0)
                db.add(st)
            old = st.state
            new, failures = apply_result(old, st.consecutive_failures, res.success, spec.fail_threshold)
            st.state, st.consecutive_failures, st.last_check_at = new, failures, done
            if res.success:
                st.last_latency_ms, st.last_error = res.latency_ms, None
            else:
                st.last_error = (res.error or "")[:250]
            if new != old:
                st.last_change_at = done
                log.warning("Servicio %s: %s -> %s", spec.id, old, new)
            db.add(ServiceResult(check_id=spec.id, checked_at=done, success=res.success,
                                 latency_ms=res.latency_ms,
                                 error=res.error[:250] if res.error else None))
        db.commit()
    return len(results)

async def main() -> None:
    setup_logging()
    logging.getLogger("httpx").setLevel(logging.WARNING)   # sus logs incluyen las URL consultadas
    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    log.info("Worker de servicios iniciado (revisa pendientes cada %ss)", settings.service_tick_s)
    while not stop.is_set():
        started = loop.time()
        try:
            n = await run_due()
            await asyncio.to_thread(beat, "services", f"{n} comprobaciones", int((loop.time() - started) * 1000))
            if n:
                log.info("%d comprobaciones ejecutadas", n)
        except Exception:
            log.exception("Fallo en el ciclo de servicios")
        wait = max(0.0, settings.service_tick_s - (loop.time() - started))
        try:
            await asyncio.wait_for(stop.wait(), timeout=wait)
        except asyncio.TimeoutError:
            pass
    log.info("Worker de servicios detenido")

if __name__ == "__main__":
    asyncio.run(main())
