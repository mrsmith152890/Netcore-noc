from collections import Counter
from datetime import datetime

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (Alert, AlertRule, Device, PingSample, ServiceCheck, ServiceResult, Site,
                        StatusEvent)
from app.modules.reports.compute import availability_pct, coverage_pct
from app.modules.reports.schema import (AlertRow, AlertsSummary, DeviceRow, PeriodInfo, Report,
                                        ServiceRow, TopDevice)

MAX_ALERT_ROWS = 1000

def _r(v, n=2):
    return None if v is None else round(float(v), n)

def build_report(db: Session, start: datetime, end: datetime, site_id: int | None) -> Report:
    db.execute(text("SET LOCAL statement_timeout = '20s'"))   # un reporte enorme no debe tumbar la API
    seconds = (end - start).total_seconds()

    # ---------- dispositivos (ICMP) ----------
    dq = select(Device, Site).join(Site, Site.id == Device.site_id).order_by(Site.name, Device.name)
    if site_id:
        dq = dq.where(Device.site_id == site_id)
    dev_rows = db.execute(dq).all()
    ids = [d.id for d, _ in dev_rows]

    ping, outages = {}, {}
    if ids:
        ping = {r.device_id: r for r in db.execute(
            select(PingSample.device_id,
                   func.count().label("n"),
                   func.count().filter(PingSample.success.is_(False)).label("failed"),
                   func.avg(PingSample.rtt_ms).filter(PingSample.success.is_(True)).label("rtt"),
                   func.avg(PingSample.packet_loss).label("loss"))
            .where(PingSample.device_id.in_(ids), PingSample.checked_at >= start, PingSample.checked_at < end)
            .group_by(PingSample.device_id))}
        outages = {did: n for did, n in db.execute(
            select(StatusEvent.device_id, func.count())
            .where(StatusEvent.device_id.in_(ids), StatusEvent.to_state == "DOWN",
                   StatusEvent.at >= start, StatusEvent.at < end)
            .group_by(StatusEvent.device_id))}

    devices: list[DeviceRow] = []
    for d, s in dev_rows:
        r = ping.get(d.id)
        if r is None and not d.enabled:
            continue
        n, failed = (r.n, r.failed) if r else (0, 0)
        devices.append(DeviceRow(
            device_id=d.id, name=d.name, ip=d.ip_address, site=s.name,
            availability_pct=availability_pct(n, failed),
            coverage_pct=coverage_pct(n, seconds, settings.probe_interval_s),
            samples=n, failed=failed, outages=outages.get(d.id, 0),
            est_downtime_s=int(failed * settings.probe_interval_s),
            avg_rtt_ms=_r(r.rtt) if r else None, avg_loss_pct=_r(r.loss) if r else None))

    # ---------- servicios ----------
    sq = (select(ServiceCheck, Device.name)
          .join(Device, Device.id == ServiceCheck.device_id)
          .order_by(Device.name, ServiceCheck.name))
    if site_id:
        sq = sq.where(Device.site_id == site_id)
    checks = db.execute(sq).all()
    cids = [c.id for c, _ in checks]

    stats, lat = {}, {}
    if cids:
        window = (ServiceResult.check_id.in_(cids), ServiceResult.checked_at >= start,
                  ServiceResult.checked_at < end)
        stats = {r.check_id: r for r in db.execute(
            select(ServiceResult.check_id, func.count().label("n"),
                   func.count().filter(ServiceResult.success.is_(False)).label("failed"))
            .where(*window).group_by(ServiceResult.check_id))}
        lat = {r.check_id: r for r in db.execute(
            select(ServiceResult.check_id, func.avg(ServiceResult.latency_ms).label("avg"),
                   func.percentile_cont(0.95).within_group(ServiceResult.latency_ms).label("p95"))
            .where(*window, ServiceResult.success.is_(True))
            .group_by(ServiceResult.check_id))}

    services: list[ServiceRow] = []
    for c, dev_name in checks:
        st = stats.get(c.id)
        if st is None and not c.enabled:
            continue
        n, failed = (st.n, st.failed) if st else (0, 0)
        lt = lat.get(c.id)
        services.append(ServiceRow(
            check_id=c.id, device=dev_name, name=c.name, kind=c.kind,
            availability_pct=availability_pct(n, failed), samples=n, failed=failed,
            avg_latency_ms=_r(lt.avg, 1) if lt else None, p95_latency_ms=_r(lt.p95, 1) if lt else None))

    # ---------- alertas ----------
    aq = (select(Alert, AlertRule, Device)
          .join(AlertRule, AlertRule.id == Alert.rule_id)
          .join(Device, Device.id == Alert.device_id)
          .where(Alert.fired_at >= start, Alert.fired_at < end)
          .order_by(Alert.fired_at.desc()).limit(MAX_ALERT_ROWS))
    if site_id:
        aq = aq.where(Device.site_id == site_id)
    alert_rows: list[AlertRow] = []
    durations: list[float] = []
    for a, rule, dev in db.execute(aq).all():
        dur = (a.resolved_at - a.fired_at).total_seconds() if a.resolved_at else None
        if dur is not None and a.resolution == "recuperada":
            durations.append(dur)
        alert_rows.append(AlertRow(
            id=a.id, device=dev.name, rule=rule.name, severity=a.severity, state=a.state,
            started_at=a.fired_at, ended_at=a.resolved_at,
            duration_s=int(dur) if dur is not None else None, detail=a.last_detail))
    top = Counter(r.device for r in alert_rows).most_common(5)
    summary = AlertsSummary(
        total=len(alert_rows),
        critical=sum(1 for r in alert_rows if r.severity == "critical"),
        warning=sum(1 for r in alert_rows if r.severity == "warning"),
        mttr_s=int(sum(durations) / len(durations)) if durations else None,
        top_devices=[TopDevice(device=n, alerts=c) for n, c in top])

    known = [d.availability_pct for d in devices if d.availability_pct is not None]
    return Report(
        period=PeriodInfo(start=start, end=end, hours=round(seconds / 3600, 1),
                          site=db.get(Site, site_id).name if site_id else None),
        avg_availability_pct=round(sum(known) / len(known), 3) if known else None,
        total_outages=sum(d.outages for d in devices),
        devices=devices, services=services, alerts=summary, alert_rows=alert_rows)
