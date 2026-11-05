from dataclasses import dataclass
from datetime import datetime

from app.modules.alerts.engine import fmt_dt, fmt_duration

@dataclass
class Check:
    key: str
    ok: bool
    detail: str

TITLES = {
    "worker:availability": "Motor de disponibilidad (ICMP)",
    "worker:snmp": "Poller SNMP",
    "worker:services": "Comprobaciones de servicios",
    "worker:alerts": "Evaluador de alertas",
    "worker:discovery": "Worker de descubrimiento",
    "backup": "Copia de seguridad",
    "restore_test": "Prueba de restauración",
    "api": "API",
    "database": "Base de datos",
    "disk": "Espacio en disco",
    "certificate": "Certificado TLS",
    "notifications": "Cola de notificaciones",
}

def check_key(worker: str) -> str:
    return worker if worker in ("backup", "restore_test") else f"worker:{worker}"

def expected_ages(s) -> dict[str, int]:
    """Antigüedad máxima aceptable del último latido de cada componente (segundos)."""
    return {
        "availability": max(60, s.probe_interval_s * 6),
        "snmp": s.snmp_interval_s * 3 + 60,
        "services": 120,
        "alerts": max(90, s.alert_eval_interval_s * 6),
        "discovery": 120,
        "backup": 26 * 3600,
        "restore_test": 8 * 86400,
    }

def heartbeat_ok(now: datetime, beat_at: datetime | None, max_age_s: float) -> tuple[bool, str]:
    if beat_at is None:
        return False, "sin latidos registrados"
    age = (now - beat_at).total_seconds()
    if age > max_age_s:
        return False, f"sin latido desde hace {fmt_duration(age)} (máximo {fmt_duration(max_age_s)})"
    return True, f"último latido hace {fmt_duration(age)}"

def disk_ok(pcts: dict[str, float], warn: int) -> tuple[bool, str]:
    detail = ", ".join(f"{path} {pct:.0f} %" for path, pct in pcts.items()) or "sin datos"
    return (max(pcts.values(), default=0) < warn), detail

def cert_ok(days_left: float | None, warn: int) -> tuple[bool, str]:
    if days_left is None:
        return True, "sin certificado local"
    return days_left >= warn, f"vence en {days_left:.0f} días"

def decide(state: str, bad_streak: int, ok_streak: int, notified_state: str | None,
           last_notified_at: datetime | None, last_attempt_at: datetime | None, now: datetime,
           confirm: int, remind_s: int, retry_s: int = 60) -> str | None:
    """¿Hay que avisar? Devuelve 'bad', 'reminder', 'ok' o None."""
    retry_ready = last_attempt_at is None or (now - last_attempt_at).total_seconds() >= retry_s
    if state == "bad" and bad_streak >= confirm:
        if notified_state != "bad":
            return "bad" if retry_ready else None
        if last_notified_at and (now - last_notified_at).total_seconds() >= remind_s:
            return "reminder" if retry_ready else None
        return None
    if state == "ok" and ok_streak >= confirm and notified_state == "bad":
        return "ok" if retry_ready else None
    return None

def format_system_message(kind: str, title: str, detail: str, since: datetime, now: datetime) -> str:
    if kind == "bad":
        return f"🛑 FALLO DEL SISTEMA · {title}\n{detail}\nDesde: {fmt_dt(since)}"
    if kind == "reminder":
        return (f"🔁 SIGUE EL FALLO · {title}\n{detail}\n"
                f"Activo hace {fmt_duration((now - since).total_seconds())} (desde {fmt_dt(since)})")
    return f"✅ SISTEMA RECUPERADO · {title}\nEl fallo duró {fmt_duration((now - since).total_seconds())}"
