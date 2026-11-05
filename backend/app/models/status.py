from datetime import datetime
from sqlalchemy import String, Boolean, Float, Integer, DateTime, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

class DeviceStatus(Base):
    """Estado operativo actual (una fila por dispositivo). Separado del inventario."""
    __tablename__ = "device_status"

    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), primary_key=True)
    state: Mapped[str] = mapped_column(String(10), default="UNKNOWN")  # UP | DOWN | UNKNOWN
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    last_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_rtt_ms: Mapped[float | None] = mapped_column(Float)
    last_change_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    wan_gateway_state: Mapped[str | None] = mapped_column(String(10))
    wan_gateway_rtt_ms: Mapped[float | None] = mapped_column(Float)
    wan_probe_state: Mapped[str | None] = mapped_column(String(10))
    wan_probe_rtt_ms: Mapped[float | None] = mapped_column(Float)
    wan_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class PingSample(Base):
    """Histórico de cada comprobación."""
    __tablename__ = "ping_samples"
    __table_args__ = (Index("ix_ping_samples_device_time", "device_id", "checked_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"))
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    success: Mapped[bool] = mapped_column(Boolean)
    rtt_ms: Mapped[float | None] = mapped_column(Float)
    packet_loss: Mapped[float] = mapped_column(Float)

class StatusEvent(Base):
    """Transiciones de estado (UP->DOWN, DOWN->UP...)."""
    __tablename__ = "status_events"
    __table_args__ = (Index("ix_status_events_device_time", "device_id", "at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    from_state: Mapped[str] = mapped_column(String(10))
    to_state: Mapped[str] = mapped_column(String(10))
