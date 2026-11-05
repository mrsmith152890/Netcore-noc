from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Site
from app.modules.reports.builder import build_report
from app.modules.reports.compute import resolve_range
from app.modules.reports.render import to_csv, to_pdf
from app.modules.reports.schema import Report

router = APIRouter(prefix="/reports", tags=["reports"])

def _aware(dt: datetime | None) -> datetime | None:
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)

def _report(db: Session, start, end, days, site_id) -> Report:
    try:
        s, e = resolve_range(_aware(start), _aware(end), days, datetime.now(timezone.utc))
    except ValueError as err:
        raise HTTPException(422, str(err))
    if site_id and not db.get(Site, site_id):
        raise HTTPException(404, "La sede no existe")
    try:
        return build_report(db, s, e, site_id)
    except OperationalError:
        db.rollback()
        raise HTTPException(504, "El reporte tardó demasiado: reduce el periodo o filtra por sede")

def _attachment(content: bytes | str, media: str, filename: str) -> Response:
    return Response(content=content, media_type=media, headers={
        "Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"})

@router.get("/availability", response_model=Report)
def availability(start: datetime | None = None, end: datetime | None = None,
                 days: int = Query(7, ge=1, le=366), site_id: int | None = None,
                 db: Session = Depends(get_db)):
    return _report(db, start, end, days, site_id)

@router.get("/availability.csv")
def availability_csv(kind: Literal["devices", "services", "alerts"] = "devices",
                     style: Literal["es", "en"] = "es",
                     start: datetime | None = None, end: datetime | None = None,
                     days: int = Query(7, ge=1, le=366), site_id: int | None = None,
                     db: Session = Depends(get_db)):
    r = _report(db, start, end, days, site_id)
    name = f"netcore-{kind}-{r.period.start:%Y%m%d}-{r.period.end:%Y%m%d}.csv"
    return _attachment(to_csv(r, kind, style), "text/csv; charset=utf-8", name)

@router.get("/availability.pdf")
def availability_pdf(start: datetime | None = None, end: datetime | None = None,
                     days: int = Query(7, ge=1, le=366), site_id: int | None = None,
                     db: Session = Depends(get_db)):
    r = _report(db, start, end, days, site_id)
    name = f"netcore-disponibilidad-{r.period.start:%Y%m%d}-{r.period.end:%Y%m%d}.pdf"
    return _attachment(to_pdf(r), "application/pdf", name)
