from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import AuditLog

router = APIRouter(prefix="/audit", tags=["audit"])

class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    at: datetime
    username: str | None
    ip: str | None
    method: str
    path: str
    status_code: int
    detail: str | None

@router.get("", response_model=list[AuditOut])
def list_audit(limit: int = Query(100, ge=1, le=500), username: str | None = None,
               db: Session = Depends(get_db)):
    q = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
    if username:
        q = q.where(AuditLog.username == username.strip().lower())
    return db.scalars(q).all()
