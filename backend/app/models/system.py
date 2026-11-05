from datetime import datetime
from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

class WorkerHeartbeat(Base):
    """Último latido de cada worker (y de las copias de seguridad)."""
    __tablename__ = "worker_heartbeats"

    worker: Mapped[str] = mapped_column(String(40), primary_key=True)
    beat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    cycle_ms: Mapped[int | None] = mapped_column(Integer)
    detail: Mapped[str | None] = mapped_column(String(255))

class SystemStatus(Base):
    """Estado de cada comprobación del vigilante y de lo que ya se avisó."""
    __tablename__ = "system_status"

    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    state: Mapped[str] = mapped_column(String(3), default="ok")        # ok | bad
    since: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    incident_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    detail: Mapped[str | None] = mapped_column(String(255))
    bad_streak: Mapped[int] = mapped_column(Integer, default=0)
    ok_streak: Mapped[int] = mapped_column(Integer, default=0)
    notified_state: Mapped[str | None] = mapped_column(String(3))     # último estado avisado
    last_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
