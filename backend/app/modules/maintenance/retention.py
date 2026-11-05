import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy import and_, delete, exists, func, select

from app.core.config import settings
from app.models import (Alert, AuditLog, DeviceMetric, DiscoveryRun, InterfaceSample, Notification,
                        PingSample, ServiceResult, StatusEvent, UserSession)

log = logging.getLogger("netcore.maintenance")

@dataclass(frozen=True)
class Rule:
    name: str
    model: type
    column: str
    days: int
    where: Callable | None = None

def cutoff_for(now: datetime, days: int) -> datetime:
    """Fecha límite de retención. Nunca menos de 1 día, para que una configuración errónea no borre todo."""
    return now - timedelta(days=max(days, 1))

def rules(s) -> list[Rule]:
    return [
        Rule("ping_samples", PingSample, "checked_at", s.retention_ping_days),
        Rule("interface_samples", InterfaceSample, "sampled_at", s.retention_interface_days),
        Rule("device_metrics", DeviceMetric, "sampled_at", s.retention_metrics_days),
        Rule("service_results", ServiceResult, "checked_at", s.retention_service_days),
        Rule("status_events", StatusEvent, "at", s.retention_events_days),
        Rule("audit_log", AuditLog, "at", s.retention_audit_days),
        Rule("notifications", Notification, "created_at", s.retention_notifications_days,
             lambda m: m.status != "pending"),
        # los hosts descubiertos se borran en cascada con su escaneo
        Rule("discovery_runs", DiscoveryRun, "created_at", s.retention_discovery_days,
             lambda m: m.status.in_(("done", "failed", "cancelled"))),
        # solo alertas resueltas y sin notificaciones pendientes de purgar
        Rule("alerts", Alert, "resolved_at", s.retention_alerts_days,
             lambda m: and_(m.state == "resolved", ~exists().where(Notification.alert_id == m.id))),
        Rule("user_sessions", UserSession, "expires_at", 7),
    ]

def purge(session_factory, now: datetime | None = None, dry_run: bool = False,
          batch: int | None = None) -> dict[str, int]:
    """Borra por lotes lo que supera la retención. Con dry_run solo cuenta."""
    now = now or datetime.now(timezone.utc)
    batch = batch or settings.retention_batch_size
    result: dict[str, int] = {}
    for r in rules(settings):
        cond = getattr(r.model, r.column) < cutoff_for(now, r.days)
        if r.where is not None:
            cond = and_(cond, r.where(r.model))
        total = 0
        if dry_run:
            with session_factory() as db:
                total = db.scalar(select(func.count()).select_from(r.model).where(cond)) or 0
        else:
            while True:
                with session_factory() as db:
                    ids = select(r.model.id).where(cond).limit(batch)
                    n = db.execute(delete(r.model).where(r.model.id.in_(ids))).rowcount or 0
                    db.commit()
                total += n
                if n < batch:
                    break
                time.sleep(0.2)          # no saturar la base con borrados continuos
        result[r.name] = total
    return result
