import asyncio
import logging
import signal
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.heartbeat import beat
from app.core.logging import setup_logging
from app.models import Device, DeviceStatus, PingSample, Site, StatusEvent
from app.modules.monitoring.probe import ping
from app.modules.monitoring.state import apply_result

log = logging.getLogger("netcore.availability")

async def run_cycle() -> None:
    with SessionLocal() as db:
        targets = db.execute(
            select(Device.id, Device.ip_address, Device.wan_gateway_ip, Device.wan_probe_ip)
            .join(Site, Site.id == Device.site_id)
            .where(Device.enabled.is_(True), Site.enabled.is_(True))
        ).all()

    sem = asyncio.Semaphore(settings.probe_concurrency)

    async def probe(dev_id: int, ip: str, gateway_ip: str | None, probe_ip: str | None):
        async with sem:
            jobs = [ping(ip, settings.ping_count, settings.ping_timeout_s)]
            jobs.append(ping(gateway_ip, 1, settings.ping_timeout_s) if gateway_ip else asyncio.sleep(0, result=None))
            jobs.append(ping(probe_ip, 1, settings.ping_timeout_s) if probe_ip else asyncio.sleep(0, result=None))
            device_result, gateway_result, external_result = await asyncio.gather(*jobs)
            return dev_id, device_result, gateway_result, external_result

    results = await asyncio.gather(*(probe(i, ip, gateway, external) for i, ip, gateway, external in targets))
    now = datetime.now(timezone.utc)

    with SessionLocal() as db:
        for dev_id, r, gateway_result, external_result in results:
            status = db.get(DeviceStatus, dev_id)
            if status is None:
                status = DeviceStatus(device_id=dev_id, state="UNKNOWN", consecutive_failures=0)
                db.add(status)

            old = status.state
            new, failures = apply_result(old, status.consecutive_failures, r.success, settings.fail_threshold)
            status.state = new
            status.consecutive_failures = failures
            status.last_check_at = now
            if r.success:
                status.last_rtt_ms = r.rtt_ms

            if new != old:
                status.last_change_at = now
                db.add(StatusEvent(device_id=dev_id, at=now, from_state=old, to_state=new))
                log.warning("Dispositivo %s: %s -> %s", dev_id, old, new)

            status.wan_gateway_state = ("UP" if gateway_result.success else "DOWN") if gateway_result else None
            status.wan_gateway_rtt_ms = gateway_result.rtt_ms if gateway_result else None
            status.wan_probe_state = ("UP" if external_result.success else "DOWN") if external_result else None
            status.wan_probe_rtt_ms = external_result.rtt_ms if external_result else None
            status.wan_checked_at = now if gateway_result or external_result else None
            db.add(PingSample(device_id=dev_id, checked_at=now, success=r.success,
                              rtt_ms=r.rtt_ms, packet_loss=r.packet_loss))
        db.commit()

    log.info("Ciclo completo: %d dispositivos", len(results))

async def main() -> None:
    setup_logging()
    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    log.info("Motor de disponibilidad iniciado (intervalo %ss, umbral DOWN %s)",
             settings.probe_interval_s, settings.fail_threshold)
    while not stop.is_set():
        started = loop.time()
        try:
            await run_cycle()
            await asyncio.to_thread(beat, "availability", None, int((loop.time() - started) * 1000))
        except Exception:
            log.exception("Fallo en el ciclo de monitoreo")
        wait = max(0.0, settings.probe_interval_s - (loop.time() - started))
        try:
            await asyncio.wait_for(stop.wait(), timeout=wait)
        except asyncio.TimeoutError:
            pass
    log.info("Motor de disponibilidad detenido")

if __name__ == "__main__":
    asyncio.run(main())
