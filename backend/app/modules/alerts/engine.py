from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.config import settings

SEVERITY_RANK = {"warning": 1, "critical": 2}

def is_fresh(ts: datetime | None, now: datetime, max_age_s: float) -> bool:
    return ts is not None and (now - ts).total_seconds() <= max_age_s

def check_condition(rule_type, threshold, status, metric, now):
    """Devuelve (condición, valor). Condición None = sin datos fiables: no se cambia nada."""
    probe_age = max(60, settings.probe_interval_s * 6)
    snmp_age = settings.snmp_interval_s * 3 + 30

    if rule_type in ("device_down", "latency_high"):
        if status is None or not is_fresh(status.last_check_at, now, probe_age):
            return None, None
        if rule_type == "device_down":
            if status.state not in ("UP", "DOWN"):
                return None, None
            return status.state == "DOWN", None
        if status.state != "UP" or status.last_rtt_ms is None:
            return None, None
        return status.last_rtt_ms > threshold, status.last_rtt_ms

    if rule_type in ("cpu_high", "mem_high"):
        if metric is None or not is_fresh(metric.sampled_at, now, snmp_age):
            return None, None
        value = metric.cpu_pct if rule_type == "cpu_high" else metric.mem_pct
        if value is None:
            return None, None
        return value > threshold, value

    return None, None

def channel_accepts(min_severity: str, severity: str) -> bool:
    return SEVERITY_RANK[severity] >= SEVERITY_RANK[min_severity]

def is_silenced(silences, rule_id: int, device_id: int, site_id: int, now: datetime) -> bool:
    for s in silences:
        if not (s.starts_at <= now < s.ends_at):
            continue
        if s.rule_id not in (None, rule_id):
            continue
        if s.device_id not in (None, device_id):
            continue
        if s.site_id not in (None, site_id):
            continue
        return True
    return False

_LABELS = {"cpu_high": "CPU", "mem_high": "Memoria"}

def describe(rule_type: str, threshold: float | None, value: float | None) -> str:
    if rule_type == "device_down":
        return "No responde a ICMP"
    thr = threshold or 0
    if rule_type == "latency_high":
        if value is None:
            return f"Latencia sobre {thr:.0f} ms"
        return f"Latencia {value:.0f} ms (umbral {thr:.0f} ms)"
    label = _LABELS.get(rule_type, rule_type)
    if value is None:
        return label
    return f"{label} al {value:.0f} % (umbral {thr:.0f} %)"

def fmt_duration(seconds: float) -> str:
    s = int(seconds)
    if s < 60:
        return f"{s} s"
    m = s // 60
    if m < 60:
        return f"{m} min"
    h, m = divmod(m, 60)
    if h < 24:
        return f"{h} h {m} min" if m else f"{h} h"
    d, h = divmod(h, 24)
    return f"{d} d {h} h" if h else f"{d} d"

def fmt_dt(dt: datetime) -> str:
    return dt.astimezone(ZoneInfo(settings.timezone)).strftime("%d/%m %H:%M")

def format_message(kind, *, rule_name, severity, device, ip, site, detail, since, now) -> str:
    critical = severity == "critical"
    heads = {
        "firing": f"{'🔴 CRÍTICO' if critical else '🟠 AVISO'} · {rule_name}",
        "reminder": f"🔁 SIGUE ACTIVA · {rule_name}",
        "escalated": f"🚨 ESCALADA A CRÍTICO · {rule_name}",
        "recovered": f"✅ RECUPERADO · {rule_name}",
    }
    lines = [heads[kind], f"{device} ({ip}) · {site}", detail]
    if kind == "firing":
        lines.append(f"Desde: {fmt_dt(since)}")
    elif kind == "recovered":
        lines.append(f"Duración: {fmt_duration((now - since).total_seconds())}")
    else:
        lines.append(f"Activa hace {fmt_duration((now - since).total_seconds())} (desde {fmt_dt(since)})")
    return "\n".join(lines)

def check_services(services, kind, now):
    """Condición de una regla service_down para un dispositivo.

    services: estados de sus comprobaciones. Devuelve (condición, detalle);
    condición None = sin datos fiables (no se cambia nada).
    """
    relevant = [s for s in services if kind is None or s.kind == kind]
    known = [s for s in relevant
             if s.state in ("UP", "DOWN") and is_fresh(s.last_check_at, now, s.interval_s * 3 + 30)]
    if not known:
        return None, None
    failing = [s for s in known if s.state == "DOWN"]
    if not failing:
        return False, None
    detail = "; ".join(f"{s.name}: {s.last_error or 'sin respuesta'}" for s in failing)
    return True, detail[:250]
