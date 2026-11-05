import hashlib
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models import User, UserSession

API_PREFIX = "/api/v1"
COOKIE = "noc_session"
ROLE_RANK = {"viewer": 1, "operator": 2, "admin": 3}
SAFE = {"GET", "HEAD", "OPTIONS"}
PUBLIC = {("GET", "/health"), ("GET", "/branding"), ("GET", "/branding/login-summary"), ("POST", "/auth/login")}
PASSWORD_CHANGE_PATHS = {"/auth/me", "/auth/logout", "/auth/password"}

# Política de acceso. Primera coincidencia gana. "WRITE" = cualquier método que modifica.
# Lo que no coincida: GET -> viewer; cualquier otro método -> admin (denegar por defecto).
_POLICY = [(m, re.compile(p), role) for m, p, role in [
    ("GET", r"^/(auth/users|audit)", "admin"),
    ("POST", r"^/auth/(logout|password)$", "viewer"),
    ("POST", r"^/alerts/\d+/ack$", "operator"),
    ("POST", r"^/alerts/silences(/\d+/expire)?$", "operator"),
    ("POST", r"^/alerts/channels/\d+/test$", "operator"),
    ("POST", r"^/discovery/scopes/\d+/runs$", "operator"),
    ("POST", r"^/discovery/runs/\d+/cancel$", "operator"),
    ("POST", r"^/services/\d+/recheck$", "operator"),
    ("POST", r"^/devices/\d+/ping$", "operator"),
    ("WRITE", r"^/maps(/|$)", "operator"),
]]

def required_role(method: str, path: str) -> str:
    for m, pattern, role in _POLICY:
        if (m == method or (m == "WRITE" and method not in SAFE)) and pattern.match(path):
            return role
    return "viewer" if method in SAFE else "admin"

def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

def client_ip(request: Request) -> str | None:
    if settings.trust_proxy:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip()[:45]
    return request.client.host if request.client else None

def _same_origin(request: Request) -> bool:
    origin = request.headers.get("origin")
    if not origin:
        return True   # peticiones que no vienen de un navegador (curl, scripts)
    return urlparse(origin).netloc == request.headers.get("host", "")

def _current(request: Request, db: Session, now: datetime):
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    s = db.scalar(select(UserSession).where(
        UserSession.token_hash == hash_token(token),
        UserSession.revoked.is_(False), UserSession.expires_at > now))
    if not s:
        return None
    max_life = timedelta(days=settings.session_max_days)
    if now - s.created_at > max_life:
        return None
    user = db.get(User, s.user_id)
    if not user or not user.enabled:
        return None
    if (now - s.last_seen_at).total_seconds() > 60:   # renovación deslizante, una escritura por minuto
        s.last_seen_at = now
        s.expires_at = min(now + timedelta(hours=settings.session_idle_hours), s.created_at + max_life)
        db.commit()
    return user, s

def authorize(request: Request, db: Session = Depends(get_db)) -> None:
    """Dependencia global: autentica, aplica la política de roles y protege contra CSRF."""
    path = request.url.path.removeprefix(API_PREFIX)
    method = request.method
    if (method, path) in PUBLIC:
        return
    found = _current(request, db, datetime.now(timezone.utc))
    if not found:
        raise HTTPException(401, "Sesión no iniciada o expirada")
    user, session = found
    request.state.user, request.state.session = user, session
    request.state.user_id, request.state.username = user.id, user.username

    if method not in SAFE and not _same_origin(request):
        raise HTTPException(403, "Origen no permitido")
    if user.must_change_password and path not in PASSWORD_CHANGE_PATHS:
        raise HTTPException(403, "password_change_required")
    if ROLE_RANK.get(user.role, 0) < ROLE_RANK[required_role(method, path)]:
        raise HTTPException(403, "No tienes permiso para esta acción")
