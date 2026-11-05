import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import COOKIE, client_ip, hash_token
from app.core.config import settings
from app.core.database import get_db
from app.core.passwords import burn_time, hash_password, needs_rehash, verify_password
from app.models import User, UserSession

router = APIRouter(prefix="/auth", tags=["auth"])

Role = Literal["viewer", "operator", "admin"]
USERNAME_RE = re.compile(r"^[a-z0-9._-]{3,32}$")
GENERIC = "Usuario o contraseña incorrectos"

def _now() -> datetime:
    return datetime.now(timezone.utc)

class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)

class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    full_name: str | None
    role: str
    enabled: bool
    must_change_password: bool
    locked_until: datetime | None
    last_login_at: datetime | None
    created_at: datetime

class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=10, max_length=128)

class UserCreate(BaseModel):
    username: str
    full_name: str | None = Field(default=None, max_length=100)
    role: Role = "viewer"
    password: str = Field(min_length=10, max_length=128)

    @field_validator("username")
    @classmethod
    def _norm(cls, v: str) -> str:
        v = v.strip().lower()
        if not USERNAME_RE.match(v):
            raise ValueError("Usuario inválido: 3-32 caracteres entre letras, números, punto, guion y guion bajo")
        return v

class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=100)
    role: Role | None = None
    enabled: bool | None = None

class ResetIn(BaseModel):
    new_password: str = Field(min_length=10, max_length=128)

def _revoke_sessions(db: Session, user_id: int, except_id: int | None = None) -> None:
    stmt = update(UserSession).where(UserSession.user_id == user_id, UserSession.revoked.is_(False))
    if except_id is not None:
        stmt = stmt.where(UserSession.id != except_id)
    db.execute(stmt.values(revoked=True))

# ---------- sesión ----------
@router.post("/login", response_model=UserOut)
def login(payload: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    now = _now()
    username = payload.username.strip().lower()
    request.state.audit_username = username
    user = db.scalar(select(User).where(User.username == username))

    if user is None or not user.enabled:
        burn_time(payload.password)
        request.state.audit_detail = "usuario inexistente o desactivado"
        raise HTTPException(401, GENERIC)
    if user.locked_until and user.locked_until > now:
        burn_time(payload.password)
        request.state.audit_detail = "cuenta bloqueada"
        raise HTTPException(401, GENERIC)
    if not verify_password(user.password_hash, payload.password):
        user.failed_logins += 1
        if user.failed_logins >= settings.login_max_failures:
            user.locked_until = now + timedelta(minutes=settings.login_lock_minutes)
            user.failed_logins = 0
            request.state.audit_detail = "clave incorrecta; cuenta bloqueada"
        else:
            request.state.audit_detail = f"clave incorrecta ({user.failed_logins})"
        db.commit()
        raise HTTPException(401, GENERIC)

    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(payload.password)
    user.failed_logins, user.locked_until, user.last_login_at = 0, None, now
    db.execute(delete(UserSession).where(UserSession.expires_at < now - timedelta(days=1)))
    token = secrets.token_urlsafe(32)
    db.add(UserSession(
        user_id=user.id, token_hash=hash_token(token), created_at=now, last_seen_at=now,
        expires_at=now + timedelta(hours=settings.session_idle_hours),
        ip=client_ip(request), user_agent=(request.headers.get("user-agent") or "")[:255]))
    db.commit()
    response.set_cookie(COOKIE, token, httponly=True, samesite="strict", secure=settings.cookie_secure,
                        path="/api", max_age=settings.session_max_days * 86400)
    request.state.audit_detail = "inicio de sesión correcto"
    return user

@router.post("/logout", status_code=204, response_class=Response)
def logout(request: Request, db: Session = Depends(get_db)):
    request.state.session.revoked = True
    db.commit()
    resp = Response(status_code=204)
    resp.delete_cookie(COOKIE, path="/api")
    return resp

@router.get("/me", response_model=UserOut)
def me(request: Request):
    return request.state.user

@router.post("/password", status_code=204, response_class=Response)
def change_password(payload: PasswordChange, request: Request, db: Session = Depends(get_db)):
    user, session = request.state.user, request.state.session
    if not verify_password(user.password_hash, payload.current_password):
        request.state.audit_detail = "clave actual incorrecta"
        raise HTTPException(400, "La contraseña actual no es correcta")
    if payload.new_password == payload.current_password:
        raise HTTPException(400, "La nueva contraseña debe ser distinta de la actual")
    if payload.new_password.lower() == user.username:
        raise HTTPException(400, "La contraseña no puede ser igual al usuario")
    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = False
    _revoke_sessions(db, user.id, except_id=session.id)   # cierra las demás sesiones
    db.commit()
    request.state.audit_detail = "contraseña cambiada"
    return Response(status_code=204)

# ---------- administración de usuarios (solo admin, ver política) ----------
@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db)):
    return db.scalars(select(User).order_by(User.username)).all()

@router.post("/users", response_model=UserOut, status_code=201)
def create_user(payload: UserCreate, request: Request, db: Session = Depends(get_db)):
    if payload.password.lower() == payload.username:
        raise HTTPException(400, "La contraseña no puede ser igual al usuario")
    user = User(username=payload.username, full_name=payload.full_name, role=payload.role,
                password_hash=hash_password(payload.password), must_change_password=True)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ese usuario ya existe")
    db.refresh(user)
    request.state.audit_detail = f"usuario={user.username} rol={user.role}"
    return user

@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, payload: UserUpdate, request: Request, db: Session = Depends(get_db)):
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(404, "Usuario no encontrado")
    data = payload.model_dump(exclude_unset=True)
    role_changes = "role" in data and data["role"] != target.role
    disables = data.get("enabled") is False
    if target.id == request.state.user.id and (role_changes or disables):
        raise HTTPException(400, "No puedes cambiar tu propio rol ni desactivarte")
    for k, v in data.items():
        setattr(target, k, v)
    if role_changes or disables:
        _revoke_sessions(db, target.id)
    db.commit()
    db.refresh(target)
    request.state.audit_detail = f"usuario={target.username} cambios={sorted(data)}"
    return target

@router.delete("/users/{user_id}", status_code=204, response_class=Response)
def delete_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(404, "Usuario no encontrado")
    if target.id == request.state.user.id:
        raise HTTPException(400, "No puedes eliminar tu propio usuario")
    if target.role == "admin" and target.enabled:
        active_admins = db.scalar(select(func.count()).select_from(User).where(
            User.role == "admin", User.enabled.is_(True))) or 0
        if active_admins <= 1:
            raise HTTPException(409, "No puedes eliminar al último administrador activo")
    username = target.username
    db.execute(delete(UserSession).where(UserSession.user_id == target.id))
    db.delete(target)
    db.commit()
    request.state.audit_detail = f"usuario eliminado={username}"
    return Response(status_code=204)

@router.post("/users/{user_id}/reset-password", status_code=204, response_class=Response)
def reset_password(user_id: int, payload: ResetIn, request: Request, db: Session = Depends(get_db)):
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(404, "Usuario no encontrado")
    if payload.new_password.lower() == target.username:
        raise HTTPException(400, "La contraseña no puede ser igual al usuario")
    target.password_hash = hash_password(payload.new_password)
    target.must_change_password = True
    target.failed_logins, target.locked_until = 0, None
    _revoke_sessions(db, target.id)
    db.commit()
    request.state.audit_detail = f"usuario={target.username} (clave temporal)"
    return Response(status_code=204)

@router.post("/users/{user_id}/unlock", response_model=UserOut)
def unlock_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(404, "Usuario no encontrado")
    target.failed_logins, target.locked_until = 0, None
    db.commit()
    db.refresh(target)
    request.state.audit_detail = f"usuario={target.username}"
    return target
