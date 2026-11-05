import asyncio
import json
import logging
import signal
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.heartbeat import beat
from app.core.logging import setup_logging
from app.core.security import decrypt
from app.models import Notification, NotificationChannel
from app.modules.alerts.evaluator import run_evaluation

log = logging.getLogger("netcore.alerts")

def _scrub(text: str, secret: str) -> str:
    return text.replace(secret, "***") if secret else text

async def send_telegram(client: httpx.AsyncClient, cfg: dict, text: str):
    """Devuelve (ok, error, retry_after, permanente)."""
    token, chat_id = cfg["bot_token"], cfg["chat_id"]
    try:
        r = await client.post(f"https://api.telegram.org/bot{token}/sendMessage",
                              json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True})
    except httpx.HTTPError as e:
        return False, _scrub(f"{type(e).__name__}: {e}", token), None, False
    try:
        body = r.json()
    except ValueError:
        body = {}
    if r.status_code == 200 and body.get("ok"):
        return True, None, None, False
    retry = (body.get("parameters") or {}).get("retry_after")
    error = _scrub(f"HTTP {r.status_code}: {body.get('description', r.text[:100])}", token)
    return False, error, retry, r.status_code in (400, 401, 403, 404)

async def dispatch_pending() -> None:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        rows = db.execute(
            select(Notification.id, NotificationChannel.type, NotificationChannel.config_enc, Notification.text)
            .join(NotificationChannel, NotificationChannel.id == Notification.channel_id)
            .where(Notification.status == "pending", Notification.next_attempt_at <= now,
                   NotificationChannel.enabled.is_(True))
            .order_by(Notification.id).limit(50)).all()
        jobs = [(nid, ctype, json.loads(decrypt(enc)), text) for nid, ctype, enc, text in rows]
    if not jobs:
        return

    results = []
    async with httpx.AsyncClient(timeout=10) as client:
        for nid, ctype, cfg, text in jobs:
            if ctype == "telegram":
                results.append((nid, *await send_telegram(client, cfg, text)))
            else:
                results.append((nid, False, f"Tipo de canal no soportado: {ctype}", None, True))
            await asyncio.sleep(0.05)   # cortesía con el límite de mensajes por segundo

    with SessionLocal() as db:
        for nid, ok, error, retry_after, permanent in results:
            n = db.get(Notification, nid)
            n.attempts += 1
            if ok:
                n.status, n.sent_at, n.last_error = "sent", datetime.now(timezone.utc), None
                log.info("Notificación %s enviada (%s)", nid, n.kind)
                continue
            n.last_error = (error or "")[:250]
            if permanent or n.attempts >= settings.notify_max_attempts:
                n.status = "failed"
                log.warning("Notificación %s fallida: %s", nid, n.last_error)
            else:
                delay = retry_after or min(30 * 2 ** (n.attempts - 1), 600)
                n.next_attempt_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
                log.warning("Notificación %s reintentará en %ss: %s", nid, delay, n.last_error)
        db.commit()

def evaluate_once() -> None:
    with SessionLocal() as db:
        run_evaluation(db, datetime.now(timezone.utc))
        db.commit()

async def main() -> None:
    setup_logging()
    logging.getLogger("httpx").setLevel(logging.WARNING)   # sus logs incluirían la URL con el token
    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    log.info("Worker de alertas iniciado (evaluación cada %ss)", settings.alert_eval_interval_s)
    while not stop.is_set():
        started = loop.time()
        try:
            evaluate_once()
            await asyncio.to_thread(beat, "alerts", None, int((loop.time() - started) * 1000))
        except Exception:
            log.exception("Fallo al evaluar alertas")
        try:
            await dispatch_pending()
        except Exception:
            log.exception("Fallo al enviar notificaciones")
        wait = max(0.0, settings.alert_eval_interval_s - (loop.time() - started))
        try:
            await asyncio.wait_for(stop.wait(), timeout=wait)
        except asyncio.TimeoutError:
            pass
    log.info("Worker de alertas detenido")

if __name__ == "__main__":
    asyncio.run(main())
