from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models import AlertRule, Device, DiscoveryScope, Silence, Site
from app.schemas.site import SiteCreate, SiteDelete, SiteOut, SiteUpdate

router = APIRouter(prefix="/sites", tags=["sites"])

def _require_admin(request: Request) -> None:
    user = getattr(request.state, "user", None)
    if not user or user.role != "admin":
        raise HTTPException(403, "Solo un administrador puede administrar sedes")


def _site_out(db: Session, site: Site) -> SiteOut:
    values = SiteOut.model_validate(site).model_dump()
    for field, model in (
        ("device_count", Device), ("scope_count", DiscoveryScope),
        ("rule_count", AlertRule), ("silence_count", Silence),
    ):
        values[field] = db.scalar(select(func.count()).select_from(model).where(model.site_id == site.id)) or 0
    return SiteOut(**values)


@router.post("", response_model=SiteOut, status_code=201)
def create_site(payload: SiteCreate, request: Request, db: Session = Depends(get_db)):
    _require_admin(request)
    site = Site(**payload.model_dump())
    db.add(site)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ya existe una sede con ese nombre")
    db.refresh(site)
    return _site_out(db, site)

@router.get("", response_model=list[SiteOut])
def list_sites(include_disabled: bool = False, db: Session = Depends(get_db)):
    q = select(Site).order_by(Site.name)
    if not include_disabled:
        q = q.where(Site.enabled.is_(True))
    return [_site_out(db, site) for site in db.scalars(q).all()]

@router.get("/{site_id}", response_model=SiteOut)
def get_site(site_id: int, db: Session = Depends(get_db)):
    site = db.get(Site, site_id)
    if not site:
        raise HTTPException(404, "Sede no encontrada")
    return _site_out(db, site)

@router.patch("/{site_id}", response_model=SiteOut)
def update_site(site_id: int, payload: SiteUpdate, request: Request, db: Session = Depends(get_db)):
    _require_admin(request)
    site = db.get(Site, site_id)
    if not site:
        raise HTTPException(404, "Sede no encontrada")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(site, key, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ya existe una sede con ese nombre")
    db.refresh(site)
    return _site_out(db, site)



@router.delete("/{site_id}", status_code=204)
def delete_site(site_id: int, request: Request, payload: SiteDelete | None = None,
                db: Session = Depends(get_db)):
    _require_admin(request)
    site = db.get(Site, site_id)
    if not site:
        raise HTTPException(404, "Sede no encontrada")

    stats = _site_out(db, site)
    related = stats.device_count + stats.scope_count + stats.rule_count + stats.silence_count
    target_id = payload.target_site_id if payload else None
    if related and target_id is None:
        raise HTTPException(
            409,
            f"La sede conserva {stats.device_count} dispositivos, {stats.scope_count} rangos, "
            f"{stats.rule_count} reglas y {stats.silence_count} silencios. Selecciona una sede destino "
            "para trasladarlos antes de eliminarla.",
        )

    if target_id is not None:
        if target_id == site_id:
            raise HTTPException(400, "La sede destino debe ser diferente")
        target = db.get(Site, target_id)
        if not target or not target.enabled:
            raise HTTPException(404, "Selecciona una sede destino activa")

        db.execute(update(Device).where(Device.site_id == site_id).values(site_id=target_id))
        db.execute(update(DiscoveryScope).where(DiscoveryScope.site_id == site_id).values(site_id=target_id))
        db.execute(update(AlertRule).where(AlertRule.site_id == site_id).values(site_id=target_id))
        db.execute(update(Silence).where(Silence.site_id == site_id).values(site_id=target_id))

    db.delete(site)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            409,
            "No se pudo completar el traslado: la sede destino ya contiene una IP o un rango duplicado. "
            "Elige otra sede destino y vuelve a intentarlo.",
        )
    return None
