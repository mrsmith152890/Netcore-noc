import logging

from app.core.database import SessionLocal
from app.models import AuditLog

log = logging.getLogger("netcore.audit")

def record_audit(*, user_id, username, ip, method, path, status_code, detail) -> None:
    """Nunca debe romper la petición: si falla, solo se registra en el log."""
    try:
        with SessionLocal() as db:
            db.add(AuditLog(user_id=user_id, username=username, ip=ip, method=method,
                            path=path[:255], status_code=status_code,
                            detail=detail[:255] if detail else None))
            db.commit()
    except Exception:
        log.exception("No se pudo registrar la auditoría")
