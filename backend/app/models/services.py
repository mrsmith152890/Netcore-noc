from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

class ServiceCheck(Base):
    """Configuración de una comprobación de servicio de un dispositivo."""
    __tablename__ = "service_checks"
    __table_args__ = (UniqueConstraint("device_id", "name", name="uq_check_device_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"))
    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(10))  # tcp | http | dns
    host: Mapped[str | None] = mapped_column(String(255))   # destino alterno (por defecto, la IP del equipo)
    port: Mapped[int | None] = mapped_column(Integer)
    url: Mapped[str | None] = mapped_column(String(500))    # admite {ip}
    expect_status: Mapped[str | None] = mapped_column(String(50))
    expect_text: Mapped[str | None] = mapped_column(String(200))
    verify_tls: Mapped[bool] = mapped_column(Boolean, default=True)
    dns_query: Mapped[str | None] = mapped_column(String(255))
    dns_type: Mapped[str] = mapped_column(String(10), default="A")
    dns_expect: Mapped[str | None] = mapped_column(String(255))
    interval_s: Mapped[int] = mapped_column(Integer, default=60)
    timeout_s: Mapped[int] = mapped_column(Integer, default=5)
    fail_threshold: Mapped[int] = mapped_column(Integer, default=3)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class ServiceStatus(Base):
    """Estado actual (separado de la configuración)."""
    __tablename__ = "service_status"

    check_id: Mapped[int] = mapped_column(ForeignKey("service_checks.id", ondelete="CASCADE"), primary_key=True)
    state: Mapped[str] = mapped_column(String(10), default="UNKNOWN")
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    last_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_latency_ms: Mapped[float | None] = mapped_column(Float)
    last_change_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(255))

class ServiceResult(Base):
    """Histórico de cada comprobación."""
    __tablename__ = "service_results"
    __table_args__ = (Index("ix_service_results_check_time", "check_id", "checked_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    check_id: Mapped[int] = mapped_column(ForeignKey("service_checks.id", ondelete="CASCADE"))
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    success: Mapped[bool] = mapped_column(Boolean)
    latency_ms: Mapped[float | None] = mapped_column(Float)
    error: Mapped[str | None] = mapped_column(String(255))
