import json
from datetime import datetime, timedelta, timezone
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decrypt, encrypt
from app.models import Alert, AlertRule, Device, Notification, NotificationChannel, Silence, Site
from app.modules.alerts.engine import describe

router = APIRouter(prefix="/alerts", tags=["alerts"])

RuleType = Literal["device_down", "cpu_high", "mem_high", "latency_high", "service_down"]
Severity = Literal["warning", "critical"]

def _now() -> datetime:
    return datetime.now(timezone.utc)

def _telegram_api(token: str, method: str) -> str:
    return f"https://api.telegram.org/bot{token}/{method}"

def _telegram_request_error(response: httpx.Response, operation: str) -> str:
    try:
        description = str(response.json().get("description", ""))
    except (ValueError, AttributeError):
        description = ""
    if response.status_code == 404 or "token" in description.lower():
        return "El token del bot es inválido o fue revocado. Crea uno nuevo con @BotFather y actualiza el canal."
    if "chat not found" in description.lower():
        return "Telegram no encuentra ese chat_id. Inicia el bot con /start o agrégalo al grupo y verifica el chat_id."
    if response.status_code == 401:
        return "Telegram rechazó las credenciales del bot. Revisa el token configurado."
    if response.status_code == 403:
        return "El bot no tiene permiso para escribir en ese chat. Revisa que no esté bloqueado y que pertenezca al grupo."
    if response.status_code == 429:
        return "Telegram limitó temporalmente las solicitudes. Espera y vuelve a intentar."
    return f"Telegram no pudo {operation} (HTTP {response.status_code}). {description[:180]}".strip()

def _validate_telegram_config(token: str, chat_id: str) -> None:
    try:
        with httpx.Client(timeout=8) as client:
            me = client.get(_telegram_api(token, "getMe"))
            data = me.json()
            if me.status_code != 200 or not data.get("ok"):
                raise HTTPException(422, _telegram_request_error(me, "validar el bot"))
            chat = client.get(_telegram_api(token, "getChat"), params={"chat_id": chat_id})
            data = chat.json()
            if chat.status_code != 200 or not data.get("ok"):
                raise HTTPException(422, _telegram_request_error(chat, "validar el chat"))
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"No se pudo conectar con Telegram: {type(exc).__name__}.") from exc

# ---------- canales ----------
class ChannelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    type: Literal["telegram"] = "telegram"
    bot_token: str = Field(min_length=10, max_length=200)
    chat_id: str = Field(min_length=1, max_length=50)
    min_severity: Severity = "warning"

class ChannelUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    min_severity: Severity | None = None
    enabled: bool | None = None
    bot_token: str | None = Field(default=None, min_length=10, max_length=200)
    chat_id: str | None = Field(default=None, min_length=1, max_length=50)

class ChannelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    type: str
    min_severity: str
    enabled: bool
    created_at: datetime

class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    alert_id: int | None
    channel_id: int
    kind: str
    status: str
    attempts: int
    created_at: datetime
    sent_at: datetime | None
    last_error: str | None
    text: str

@router.post("/channels", response_model=ChannelOut, status_code=201)
def create_channel(payload: ChannelCreate, db: Session = Depends(get_db)):
    _validate_telegram_config(payload.bot_token.strip(), payload.chat_id.strip())
    cfg = json.dumps({"bot_token": payload.bot_token.strip(), "chat_id": payload.chat_id.strip()})
    ch = NotificationChannel(name=payload.name, type=payload.type, config_enc=encrypt(cfg),
                             min_severity=payload.min_severity)
    db.add(ch)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ya existe un canal con ese nombre")
    db.refresh(ch)
    return ch

@router.get("/channels", response_model=list[ChannelOut])
def list_channels(db: Session = Depends(get_db)):
    return db.scalars(select(NotificationChannel).order_by(NotificationChannel.id)).all()

@router.patch("/channels/{channel_id}", response_model=ChannelOut)
def update_channel(channel_id: int, payload: ChannelUpdate, db: Session = Depends(get_db)):
    ch = db.get(NotificationChannel, channel_id)
    if not ch:
        raise HTTPException(404, "Canal no encontrado")
    data = payload.model_dump(exclude_unset=True)
    token, chat = data.pop("bot_token", None), data.pop("chat_id", None)
    if token or chat:
        cfg = json.loads(decrypt(ch.config_enc))
        if token:
            cfg["bot_token"] = token.strip()
        if chat:
            cfg["chat_id"] = chat.strip()
        _validate_telegram_config(cfg["bot_token"], cfg["chat_id"])
        ch.config_enc = encrypt(json.dumps(cfg))
    for k, v in data.items():
        setattr(ch, k, v)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ya existe un canal con ese nombre")
    db.refresh(ch)
    return ch

@router.post("/channels/{channel_id}/test", response_model=NotificationOut, status_code=201)
def test_channel(channel_id: int, db: Session = Depends(get_db)):
    """Envía inmediatamente una prueba y registra el resultado antes de responder."""
    ch = db.get(NotificationChannel, channel_id)
    if not ch:
        raise HTTPException(404, "Canal no encontrado")
    if not ch.enabled:
        raise HTTPException(400, "El canal está desactivado")
    cfg = json.loads(decrypt(ch.config_enc))
    token, chat_id = cfg["bot_token"], cfg["chat_id"]
    n = Notification(alert_id=None, channel_id=ch.id, kind="test", status="pending", next_attempt_at=_now(),
                     text=f"🔔 Prueba de NetCore NOC: el canal «{ch.name}» funciona.")
    db.add(n)
    db.flush()
    try:
        _validate_telegram_config(token, chat_id)
        with httpx.Client(timeout=8) as client:
            response = client.post(_telegram_api(token, "sendMessage"),
                                   json={"chat_id": chat_id, "text": n.text, "disable_web_page_preview": True})
        try:
            result = response.json()
        except ValueError:
            result = {}
        if response.status_code != 200 or not result.get("ok"):
            detail = _telegram_request_error(response, "enviar el mensaje de prueba")
            n.status, n.attempts, n.last_error = "failed", 1, detail[:250]
            db.commit()
            raise HTTPException(502, detail)
        n.status, n.attempts, n.sent_at, n.last_error = "sent", 1, _now(), None
        db.commit()
        db.refresh(n)
        return n
    except HTTPException as exc:
        if n.status == "pending":
            n.status, n.attempts, n.last_error = "failed", 1, str(exc.detail)[:250]
            db.commit()
        raise
    except httpx.HTTPError as exc:
        detail = f"No se pudo conectar con Telegram: {type(exc).__name__}."
        n.status, n.attempts, n.last_error = "failed", 1, detail
        db.commit()
        raise HTTPException(502, detail) from exc

@router.get("/notifications", response_model=list[NotificationOut])
def list_notifications(limit: int = Query(30, ge=1, le=200), db: Session = Depends(get_db)):
    return db.scalars(select(Notification).order_by(Notification.id.desc()).limit(limit)).all()

# ---------- reglas ----------
class RuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    rule_type: RuleType
    threshold: float | None = None
    for_seconds: int = Field(default=0, ge=0, le=86400)
    recover_after_s: int = Field(default=60, ge=0, le=86400)
    severity: Severity = "warning"
    site_id: int | None = None
    device_id: int | None = None
    check_type: Literal["tcp", "http", "dns"] | None = None
    repeat_interval_s: int = Field(default=3600, ge=0, le=604800)
    escalate_after_s: int | None = Field(default=None, ge=60, le=604800)
    enabled: bool = True

class RuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    threshold: float | None = None
    for_seconds: int | None = Field(default=None, ge=0, le=86400)
    recover_after_s: int | None = Field(default=None, ge=0, le=86400)
    severity: Severity | None = None
    repeat_interval_s: int | None = Field(default=None, ge=0, le=604800)
    escalate_after_s: int | None = Field(default=None, ge=60, le=604800)
    enabled: bool | None = None

class RuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    rule_type: str
    threshold: float | None
    for_seconds: int
    recover_after_s: int
    severity: str
    site_id: int | None
    device_id: int | None
    check_type: str | None
    repeat_interval_s: int
    escalate_after_s: int | None
    enabled: bool

def _check_threshold(rule_type: str, threshold: float | None) -> float | None:
    if rule_type in ("device_down", "service_down"):
        return None
    if threshold is None or threshold <= 0:
        raise HTTPException(422, "Esta regla requiere un umbral mayor que 0")
    if rule_type in ("cpu_high", "mem_high") and threshold > 100:
        raise HTTPException(422, "El umbral debe estar entre 0 y 100")
    return threshold

@router.post("/rules", response_model=RuleOut, status_code=201)
def create_rule(payload: RuleCreate, db: Session = Depends(get_db)):
    if payload.site_id and not db.get(Site, payload.site_id):
        raise HTTPException(404, "La sede no existe")
    if payload.device_id and not db.get(Device, payload.device_id):
        raise HTTPException(404, "El dispositivo no existe")
    data = payload.model_dump()
    data["threshold"] = _check_threshold(payload.rule_type, payload.threshold)
    rule = AlertRule(**data)
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule

@router.get("/rules", response_model=list[RuleOut])
def list_rules(db: Session = Depends(get_db)):
    return db.scalars(select(AlertRule).order_by(AlertRule.id)).all()

@router.patch("/rules/{rule_id}", response_model=RuleOut)
def update_rule(rule_id: int, payload: RuleUpdate, db: Session = Depends(get_db)):
    rule = db.get(AlertRule, rule_id)
    if not rule:
        raise HTTPException(404, "Regla no encontrada")
    data = payload.model_dump(exclude_unset=True)
    if "threshold" in data:
        data["threshold"] = _check_threshold(rule.rule_type, data["threshold"])
    for k, v in data.items():
        setattr(rule, k, v)
    db.commit()
    db.refresh(rule)
    return rule

# ---------- silencios ----------
class SilenceCreate(BaseModel):
    rule_id: int | None = None
    device_id: int | None = None
    site_id: int | None = None
    minutes: int | None = Field(default=None, ge=1, le=10080)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    reason: str = Field(min_length=1, max_length=255)

    @model_validator(mode="after")
    def _needs_matcher(self):
        if self.rule_id is None and self.device_id is None and self.site_id is None:
            raise ValueError("Indica al menos una regla, dispositivo o sede a silenciar")
        if (self.starts_at is None) != (self.ends_at is None):
            raise ValueError("Indica fecha y hora de inicio y fin")
        if self.starts_at is None and self.minutes is None:
            raise ValueError("Indica la duración o el horario programado")
        if self.starts_at and self.ends_at:
            start = self.starts_at if self.starts_at.tzinfo else self.starts_at.replace(tzinfo=timezone.utc)
            end = self.ends_at if self.ends_at.tzinfo else self.ends_at.replace(tzinfo=timezone.utc)
            if end <= start:
                raise ValueError("El fin debe ser posterior al inicio")
            if (end - start).total_seconds() > 7 * 86400:
                raise ValueError("La ventana no puede superar 7 días")
        return self

class SilenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    rule_id: int | None
    device_id: int | None
    site_id: int | None
    starts_at: datetime
    ends_at: datetime
    reason: str
    created_at: datetime

@router.post("/silences", response_model=SilenceOut, status_code=201)
def create_silence(payload: SilenceCreate, db: Session = Depends(get_db)):
    if payload.rule_id and not db.get(AlertRule, payload.rule_id):
        raise HTTPException(404, "La regla no existe")
    if payload.device_id and not db.get(Device, payload.device_id):
        raise HTTPException(404, "El dispositivo no existe")
    if payload.site_id and not db.get(Site, payload.site_id):
        raise HTTPException(404, "La sede no existe")
    now = _now()
    starts_at = payload.starts_at or now
    if starts_at.tzinfo is None:
        starts_at = starts_at.replace(tzinfo=timezone.utc)
    if payload.ends_at:
        ends_at = payload.ends_at if payload.ends_at.tzinfo else payload.ends_at.replace(tzinfo=timezone.utc)
    else:
        ends_at = starts_at + timedelta(minutes=payload.minutes or 60)
    s = Silence(rule_id=payload.rule_id, device_id=payload.device_id, site_id=payload.site_id,
                starts_at=starts_at, ends_at=ends_at, reason=payload.reason.strip())
    db.add(s)
    db.commit()
    db.refresh(s)
    return s

@router.get("/silences", response_model=list[SilenceOut])
def list_silences(only_active: bool = True, db: Session = Depends(get_db)):
    q = select(Silence).order_by(Silence.id.desc()).limit(100)
    if only_active:
        q = q.where(Silence.ends_at > _now())
    return db.scalars(q).all()

@router.post("/silences/{silence_id}/expire", response_model=SilenceOut)
def expire_silence(silence_id: int, db: Session = Depends(get_db)):
    s = db.get(Silence, silence_id)
    if not s:
        raise HTTPException(404, "Silencio no encontrado")
    s.ends_at = min(s.ends_at, _now())
    db.commit()
    db.refresh(s)
    return s

# ---------- alertas ----------
class AlertOut(BaseModel):
    id: int
    rule_id: int
    rule_name: str
    rule_type: str
    severity: str
    state: str
    device_id: int
    device_name: str
    device_ip: str
    site_name: str
    created_at: datetime
    fired_at: datetime | None
    acked_at: datetime | None
    ack_note: str | None
    resolved_at: datetime | None
    resolution: str | None
    last_value: float | None
    escalated: bool
    summary: str

class AckIn(BaseModel):
    note: str | None = Field(default=None, max_length=255)

def _alert_out(a: Alert, rule: AlertRule, dev: Device, site: Site) -> AlertOut:
    return AlertOut(
        id=a.id, rule_id=rule.id, rule_name=rule.name, rule_type=rule.rule_type, severity=a.severity,
        state=a.state, device_id=dev.id, device_name=dev.name, device_ip=dev.ip_address,
        site_name=site.name, created_at=a.created_at, fired_at=a.fired_at, acked_at=a.acked_at,
        ack_note=a.ack_note, resolved_at=a.resolved_at, resolution=a.resolution,
        last_value=a.last_value, escalated=a.escalated,
        summary=a.last_detail or describe(rule.rule_type, rule.threshold, a.last_value))

@router.get("", response_model=list[AlertOut])
def list_alerts(state: Literal["active", "pending", "resolved", "all"] = "active",
                limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db)):
    q = (select(Alert, AlertRule, Device, Site)
         .join(AlertRule, AlertRule.id == Alert.rule_id)
         .join(Device, Device.id == Alert.device_id)
         .join(Site, Site.id == Device.site_id))
    if state == "active":
        q = q.where(Alert.state.in_(["firing", "acknowledged"]))
    elif state in ("pending", "resolved"):
        q = q.where(Alert.state == state)
    q = q.order_by(Alert.id.desc()).limit(limit)
    return [_alert_out(a, r, d, s) for a, r, d, s in db.execute(q).all()]

@router.post("/{alert_id}/ack", response_model=AlertOut)
def ack_alert(alert_id: int, payload: AckIn, db: Session = Depends(get_db)):
    a = db.get(Alert, alert_id)
    if not a:
        raise HTTPException(404, "Alerta no encontrada")
    if a.state != "firing":
        raise HTTPException(409, "Solo se pueden reconocer alertas activas sin reconocer")
    a.state, a.acked_at, a.ack_note = "acknowledged", _now(), payload.note
    db.commit()
    rule, dev = db.get(AlertRule, a.rule_id), db.get(Device, a.device_id)
    return _alert_out(a, rule, dev, db.get(Site, dev.site_id))
