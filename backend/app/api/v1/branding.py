import base64
import binascii
import re

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Alert, AppBranding, Device, DeviceStatus

router = APIRouter(prefix="/branding", tags=["branding"])
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_DATA_URL_LENGTH = 7000100


class BrandingOut(BaseModel):
    logo_data: str | None = None
    favicon_data: str | None = None
    login_art_data: str | None = None
    login_status_enabled: bool = False


class LoginSummaryOut(BaseModel):
    enabled: bool
    devices_total: int = 0
    devices_up: int = 0
    devices_down: int = 0
    alerts_active: int = 0
    alerts_critical: int = 0


class BrandingUpdate(BaseModel):
    logo_data: str | None = Field(default=None, max_length=MAX_DATA_URL_LENGTH)
    favicon_data: str | None = Field(default=None, max_length=MAX_DATA_URL_LENGTH)
    login_art_data: str | None = Field(default=None, max_length=MAX_DATA_URL_LENGTH)
    login_status_enabled: bool | None = None

    @field_validator("logo_data", "favicon_data", "login_art_data")
    @classmethod
    def validate_image(cls, value: str | None) -> str | None:
        if value is None:
            return None
        match = re.fullmatch(r"data:image/(png|jpeg|webp|svg\+xml);base64,([A-Za-z0-9+/]*={0,2})", value)
        if not match:
            raise ValueError("Usa una imagen PNG, JPEG, WebP o SVG")
        mime, encoded = match.groups()
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("La imagen no tiene una codificación válida") from exc
        if not raw or len(raw) > MAX_IMAGE_BYTES:
            raise ValueError("Cada imagen debe pesar como máximo 5 MB")
        if mime == "png" and not raw.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("El archivo no es un PNG válido")
        if mime == "jpeg" and not raw.startswith(b"\xff\xd8\xff"):
            raise ValueError("El archivo no es un JPEG válido")
        if mime == "webp" and (raw[:4] != b"RIFF" or raw[8:12] != b"WEBP"):
            raise ValueError("El archivo no es un WebP válido")
        if mime == "svg+xml":
            import xml.etree.ElementTree as ET
            try:
                text = raw.decode("utf-8")
                if re.search(r"<!\s*(DOCTYPE|ENTITY)", text, re.IGNORECASE):
                    raise ValueError("El SVG no puede contener entidades ni DTD")
                ET.fromstring(text)
            except (UnicodeDecodeError, ET.ParseError) as exc:
                raise ValueError("El archivo no es un SVG válido") from exc
        return value


def _out(row: AppBranding | None) -> BrandingOut:
    return BrandingOut(
        logo_data=row.logo_data if row else None,
        favicon_data=row.favicon_data if row else None,
        login_art_data=row.login_art_data if row else None,
        login_status_enabled=row.login_status_enabled if row else False,
    )


@router.get("", response_model=BrandingOut)
def get_branding(db: Session = Depends(get_db)):
    return _out(db.get(AppBranding, 1))


@router.get("/login-summary", response_model=LoginSummaryOut)
def login_summary(db: Session = Depends(get_db)):
    branding = db.get(AppBranding, 1)
    if not branding or not branding.login_status_enabled:
        return LoginSummaryOut(enabled=False)

    devices_total = db.scalar(select(func.count(Device.id)).where(Device.enabled.is_(True))) or 0
    state_rows = db.execute(
        select(DeviceStatus.state, func.count())
        .join(Device, Device.id == DeviceStatus.device_id)
        .where(Device.enabled.is_(True))
        .group_by(DeviceStatus.state)
    ).all()
    states = {state: count for state, count in state_rows}
    devices_up = states.get("UP", 0)
    devices_down = states.get("DOWN", 0)
    active_states = ("firing", "acknowledged")
    alerts_active = db.scalar(select(func.count(Alert.id)).where(Alert.state.in_(active_states))) or 0
    alerts_critical = db.scalar(select(func.count(Alert.id)).where(
        Alert.state.in_(active_states), Alert.severity == "critical"
    )) or 0
    return LoginSummaryOut(
        enabled=True, devices_total=devices_total, devices_up=devices_up,
        devices_down=devices_down, alerts_active=alerts_active, alerts_critical=alerts_critical,
    )


@router.patch("", response_model=BrandingOut)
def update_branding(payload: BrandingUpdate, db: Session = Depends(get_db)):
    row = db.get(AppBranding, 1)
    if row is None:
        row = AppBranding(id=1)
        db.add(row)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return _out(row)
