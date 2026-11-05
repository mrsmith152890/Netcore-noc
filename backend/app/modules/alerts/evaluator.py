from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (Alert, AlertRule, Device, DeviceMetric, DeviceStatus, Notification,
                        NotificationChannel, ServiceCheck, ServiceStatus, Silence, Site)
from app.modules.alerts.engine import (channel_accepts, check_condition, check_services, describe,
                                       format_message, is_silenced)

@dataclass
class Ctx:
    now: datetime
    channels: list
    silences: list

def _latest_metrics(db: Session, ids: list[int], now: datetime) -> dict[int, DeviceMetric]:
    if not ids:
        return {}
    since = now - timedelta(seconds=max(600, settings.snmp_interval_s * 5))
    q = (select(DeviceMetric)
         .where(DeviceMetric.device_id.in_(ids), DeviceMetric.sampled_at >= since)
         .distinct(DeviceMetric.device_id)
         .order_by(DeviceMetric.device_id, DeviceMetric.sampled_at.desc()))
    return {m.device_id: m for m in db.scalars(q)}

def _services_by_device(db: Session) -> dict[int, list]:
    rows = db.execute(
        select(ServiceCheck.device_id, ServiceCheck.name, ServiceCheck.kind, ServiceCheck.interval_s,
               ServiceStatus.state, ServiceStatus.last_check_at, ServiceStatus.last_error)
        .join(ServiceStatus, ServiceStatus.check_id == ServiceCheck.id)
        .where(ServiceCheck.enabled.is_(True))).all()
    out: dict[int, list] = {}
    for r in rows:
        out.setdefault(r.device_id, []).append(r)
    return out

def _notify(db, ctx, alert, rule, dev, site, kind, detail, targets: set[int] | None = None) -> None:
    text = format_message(kind, rule_name=rule.name, severity=alert.severity, device=dev.name,
                          ip=dev.ip_address, site=site.name, detail=detail,
                          since=alert.fired_at or alert.created_at, now=ctx.now)
    silenced = is_silenced(ctx.silences, rule.id, dev.id, dev.site_id, ctx.now)
    for ch in ctx.channels:
        if targets is not None and ch.id not in targets:
            continue
        if not channel_accepts(ch.min_severity, alert.severity):
            continue
        db.add(Notification(alert_id=alert.id, channel_id=ch.id, kind=kind, text=text,
                            status="suppressed" if silenced else "pending",
                            next_attempt_at=ctx.now))
    alert.last_notified_at = ctx.now

def _on_true(db, ctx, active, rule, dev, site, alert, value, detail_text=None) -> None:
    now = ctx.now
    if alert is None:
        alert = Alert(rule_id=rule.id, device_id=dev.id, state="pending",
                      severity=rule.severity, created_at=now, last_value=value)
        db.add(alert)
        active[(rule.id, dev.id)] = alert
    else:
        alert.clear_since = None
        alert.last_value = value
    alert.last_detail = detail_text

    detail = detail_text or describe(rule.rule_type, rule.threshold, value)
    if alert.state == "pending":
        if (now - alert.created_at).total_seconds() >= rule.for_seconds:
            alert.state, alert.fired_at = "firing", now
            db.flush()
            _notify(db, ctx, alert, rule, dev, site, "firing", detail)
    elif alert.state == "firing":   # las reconocidas no escalan ni recuerdan
        age = (now - alert.fired_at).total_seconds()
        since_last = (now - alert.last_notified_at).total_seconds() if alert.last_notified_at else age
        if (rule.escalate_after_s and not alert.escalated
                and alert.severity != "critical" and age >= rule.escalate_after_s):
            alert.escalated, alert.severity = True, "critical"
            _notify(db, ctx, alert, rule, dev, site, "escalated", detail)
        elif rule.repeat_interval_s and since_last >= rule.repeat_interval_s:
            _notify(db, ctx, alert, rule, dev, site, "reminder", detail)

def _on_false(db, ctx, active, rule, dev, site, alert) -> None:
    if alert is None:
        return
    now = ctx.now
    if alert.state == "pending":     # nunca llegó a disparar: se descarta sin ruido
        db.delete(alert)
        active.pop((rule.id, dev.id), None)
        return
    if alert.clear_since is None:
        alert.clear_since = now
    if (now - alert.clear_since).total_seconds() >= rule.recover_after_s:
        alert.state, alert.resolved_at, alert.resolution = "resolved", now, "recuperada"
        announced = {n.channel_id for n in db.scalars(select(Notification).where(
            Notification.alert_id == alert.id,
            Notification.kind.in_(["firing", "escalated", "reminder"]),
            Notification.status.in_(["pending", "sent"])))}
        if announced:   # solo se avisa la recuperación de lo que se avisó
            _notify(db, ctx, alert, rule, dev, site, "recovered", "Condición normalizada", targets=announced)
        active.pop((rule.id, dev.id), None)

def run_evaluation(db: Session, now: datetime) -> None:
    rules = list(db.scalars(select(AlertRule).where(AlertRule.enabled.is_(True))))
    ctx = Ctx(
        now=now,
        channels=list(db.scalars(select(NotificationChannel).where(NotificationChannel.enabled.is_(True)))),
        silences=list(db.scalars(select(Silence).where(Silence.ends_at > now))),
    )
    rows = db.execute(
        select(Device, Site, DeviceStatus)
        .join(Site, Site.id == Device.site_id)
        .outerjoin(DeviceStatus, DeviceStatus.device_id == Device.id)
        .where(Device.enabled.is_(True), Site.enabled.is_(True))).all()
    metrics = _latest_metrics(db, [d.id for d, _, _ in rows], now)
    services = _services_by_device(db)
    active = {(a.rule_id, a.device_id): a
              for a in db.scalars(select(Alert).where(Alert.state != "resolved"))}
    seen: set[tuple[int, int]] = set()

    for rule in rules:
        for dev, site, status in rows:
            if rule.site_id and rule.site_id != dev.site_id:
                continue
            if rule.device_id and rule.device_id != dev.id:
                continue
            key = (rule.id, dev.id)
            seen.add(key)
            if rule.rule_type == "service_down":
                cond, detail_text = check_services(services.get(dev.id, []), rule.check_type, now)
                value = None
            else:
                cond, value = check_condition(rule.rule_type, rule.threshold, status, metrics.get(dev.id), now)
                detail_text = None
            if cond is None:
                continue
            alert = active.get(key)
            if cond:
                _on_true(db, ctx, active, rule, dev, site, alert, value, detail_text)
            else:
                _on_false(db, ctx, active, rule, dev, site, alert)

    # alertas cuya regla se desactivó o cuyo dispositivo salió del monitoreo
    for key, alert in list(active.items()):
        if key not in seen:
            alert.state, alert.resolved_at, alert.resolution = "resolved", now, "auto-cerrada"
