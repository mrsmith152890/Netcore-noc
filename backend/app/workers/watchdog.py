import asyncio
import json
import logging
import shutil
import signal
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import httpx
from sqlalchemy import func, select

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.logging import setup_logging
from app.core.security import decrypt
from app.models import Notification, NotificationChannel, SystemStatus, WorkerHeartbeat
from app.modules.system.health import (TITLES, Check, cert_ok, check_key, decide, disk_ok, expected_ages,
                                       format_system_message, heartbeat_ok)
from app.workers.alerts import send_telegram

log = logging.getLogger("netcore.watchdog")
CERT_PATH = "/etc/ssl/netcore/netcore.crt"
STARTED = datetime.now(timezone.utc)
GRACE_S = 120
NO_GRACE = ("backup", "restore_test")

@dataclass
class Mem:
    """Estado en memoria: permite avisar aunque la base de datos esté caída."""
    channels: list = field(default_factory=list)
    grace_until: datetime | None = None
    db: SimpleNamespace = field(default_factory=lambda: SimpleNamespace(
        state="ok", bad_streak=0, ok_streak=0, notified_state=None, last_notified_at=None,
        last_attempt_at=None, incident_at=None, since=STARTED))

def disk_percentages() -> dict[str, float]:
    out = {}
    for path in ("/", "/var/backups"):
        try:
            u = shutil.disk_usage(path)
            out[path] = u.used * 100 / u.total
        except OSError:
            pass
    return out

def cert_days_left() -> float | None:
    p = Path(CERT_PATH)
    if not p.exists():
        return None
    from cryptography import x509
    cert = x509.load_pem_x509_certificate(p.read_bytes())
    end = getattr(cert, "not_valid_after_utc", None) or cert.not_valid_after.replace(tzinfo=timezone.utc)
    return (end - datetime.now(timezone.utc)).total_seconds() / 86400

def collect_checks(now: datetime, grace: bool) -> tuple[list[Check], list[dict]]:
    """Comprobaciones que dependen de la base de datos. Lanza excepción si no hay conexión."""
    ages = expected_ages(settings)
    channels: list[dict] = []
    with SessionLocal() as db:
        db.execute(select(1))
        beats = {b.worker: b for b in db.scalars(select(WorkerHeartbeat))}
        backlog = db.scalar(select(func.count()).select_from(Notification).where(
            Notification.status == "pending",
            Notification.created_at < now - timedelta(minutes=10))) or 0
        for ch in db.scalars(select(NotificationChannel).where(NotificationChannel.enabled.is_(True))):
            try:
                channels.append({"id": ch.id, "name": ch.name, "type": ch.type,
                                 "cfg": json.loads(decrypt(ch.config_enc))})
            except Exception:
                log.warning("No se pudo leer la configuración del canal %s", ch.id)

    checks = [Check("database", True, "conexión correcta")]
    for worker, max_age in ages.items():
        b = beats.get(worker)
        ok, detail = heartbeat_ok(now, b.beat_at if b else None, max_age)
        if worker not in NO_GRACE:
            if grace:
                ok, detail = True, "recuperándose tras una caída de la base de datos"
            elif b is None and (now - STARTED).total_seconds() < GRACE_S:
                ok, detail = True, "arrancando"
        checks.append(Check(check_key(worker), ok, detail))
    checks.append(Check("disk", *disk_ok(disk_percentages(), settings.disk_warn_pct)))
    checks.append(Check("certificate", *cert_ok(cert_days_left(), settings.cert_warn_days)))
    checks.append(Check("notifications", backlog == 0,
                        "sin cola atascada" if backlog == 0 else f"{backlog} notificaciones pendientes hace más de 10 min"))
    return checks, channels

def update_states(checks: list[Check], now: datetime) -> list[dict]:
    """Actualiza el estado de cada comprobación y devuelve lo que hay que avisar."""
    out = []
    with SessionLocal() as db:
        for c in checks:
            row = db.get(SystemStatus, c.key)
            if row is None:
                row = SystemStatus(key=c.key, state="ok", since=now, checked_at=now, bad_streak=0, ok_streak=0)
                db.add(row)
            new = "ok" if c.ok else "bad"
            if row.state != new:
                row.state, row.since = new, now
                if new == "bad":
                    row.incident_at = now
            row.detail, row.checked_at = c.detail[:255], now
            if new == "bad":
                row.bad_streak, row.ok_streak = min(row.bad_streak + 1, 1000), 0
            else:
                row.ok_streak, row.bad_streak = min(row.ok_streak + 1, 1000), 0
            kind = decide(row.state, row.bad_streak, row.ok_streak, row.notified_state,
                          row.last_notified_at, row.last_attempt_at, now,
                          settings.watchdog_confirm, settings.watchdog_remind_s)
            if kind:
                out.append({"key": c.key, "kind": kind, "detail": row.detail,
                            "since": row.incident_at or row.since})
        db.commit()
    return out

def record_result(item: dict, results: list, text: str, now: datetime) -> None:
    delivered = (not results) or any(ok for _cid, ok, _err in results)
    with SessionLocal() as db:
        row = db.get(SystemStatus, item["key"])
        row.last_attempt_at = now
        if delivered:
            row.notified_state = "ok" if item["kind"] == "ok" else "bad"
            row.last_notified_at = now
        for cid, ok, err in results:
            db.add(Notification(alert_id=None, channel_id=cid, kind="system", text=text,
                                status="sent" if ok else "failed", attempts=1, next_attempt_at=now,
                                sent_at=now if ok else None, last_error=(err or "")[:250] or None))
        db.commit()

async def send_all(client: httpx.AsyncClient, channels: list[dict], text: str) -> list:
    results = []
    for ch in channels:
        if ch["type"] != "telegram":
            continue
        ok, err, _retry, _perm = await send_telegram(client, ch["cfg"], text)
        results.append((ch["id"], ok, err))
    if not channels:
        log.warning("No hay canales de notificación configurados: no se puede avisar")
    return results

async def check_api(client: httpx.AsyncClient) -> Check:
    try:
        r = await client.get("http://127.0.0.1:8000/api/v1/health", timeout=5)
        return Check("api", r.status_code == 200, "responde" if r.status_code == 200 else f"HTTP {r.status_code}")
    except httpx.HTTPError as e:
        return Check("api", False, f"sin respuesta ({type(e).__name__})")

async def ping_external(client: httpx.AsyncClient) -> None:
    if not settings.heartbeat_url:
        return
    try:
        await client.get(settings.heartbeat_url, timeout=10)
    except httpx.HTTPError:
        log.debug("No se pudo contactar el servicio externo de latido")

async def cycle(client: httpx.AsyncClient, mem: Mem) -> None:
    now = datetime.now(timezone.utc)
    await ping_external(client)
    api_check = await check_api(client)

    db_up, db_detail = True, "conexión correcta"
    checks: list[Check] = []
    try:
        grace = bool(mem.grace_until and now < mem.grace_until)
        checks, channels = await asyncio.to_thread(collect_checks, now, grace)
        mem.channels = channels
    except Exception as e:
        db_up, db_detail = False, f"No se pudo consultar la base de datos ({type(e).__name__})"

    # La base de datos se vigila en memoria: es lo único que no puede registrarse en la propia base.
    st = mem.db
    if db_up:
        if st.state == "bad":
            mem.grace_until = now + timedelta(seconds=GRACE_S)    # los workers necesitan un ciclo para volver a latir
            st.since = now
        st.state, st.ok_streak, st.bad_streak = "ok", st.ok_streak + 1, 0
    else:
        if st.state == "ok":
            st.since, st.incident_at = now, now
        st.state, st.bad_streak, st.ok_streak = "bad", st.bad_streak + 1, 0
        log.error(db_detail)
    kind = decide(st.state, st.bad_streak, st.ok_streak, st.notified_state, st.last_notified_at,
                  st.last_attempt_at, now, settings.watchdog_confirm, settings.watchdog_remind_s)
    if kind:
        text = format_system_message(kind, TITLES["database"], db_detail, st.incident_at or st.since, now)
        results = await send_all(client, mem.channels, text)
        st.last_attempt_at = now
        if (not results) or any(ok for _c, ok, _e in results):
            st.notified_state = "ok" if kind == "ok" else "bad"
            st.last_notified_at = now
    if not db_up:
        return

    checks.append(api_check)
    for item in await asyncio.to_thread(update_states, checks, now):
        text = format_system_message(item["kind"], TITLES.get(item["key"], item["key"]),
                                     item["detail"], item["since"], now)
        results = await send_all(client, mem.channels, text)
        await asyncio.to_thread(record_result, item, results, text, now)

async def main() -> None:
    setup_logging()
    logging.getLogger("httpx").setLevel(logging.WARNING)   # las URL (token de Telegram, latido externo) no deben ir al log
    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    mem = Mem()
    log.info("Vigilante iniciado (cada %ss)", settings.watchdog_interval_s)
    async with httpx.AsyncClient(timeout=10) as client:
        while not stop.is_set():
            started = loop.time()
            try:
                await cycle(client, mem)
            except Exception:
                log.exception("Fallo en el ciclo del vigilante")
            wait = max(0.0, settings.watchdog_interval_s - (loop.time() - started))
            try:
                await asyncio.wait_for(stop.wait(), timeout=wait)
            except asyncio.TimeoutError:
                pass
    log.info("Vigilante detenido")

if __name__ == "__main__":
    asyncio.run(main())
