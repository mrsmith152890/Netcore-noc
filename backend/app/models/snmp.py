from datetime import datetime
from sqlalchemy import (BigInteger, Boolean, DateTime, Float, ForeignKey, Index, Integer,
                        String, Text, UniqueConstraint, func)
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

class SnmpCredential(Base):
    """Configuración SNMP del dispositivo (la comunidad va cifrada)."""
    __tablename__ = "snmp_credentials"

    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), primary_key=True)
    version: Mapped[str] = mapped_column(String(5), default="2c")
    port: Mapped[int] = mapped_column(Integer, default=161)
    community_enc: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class SnmpIdentity(Base):
    """Identidad y estado de la última consulta SNMP."""
    __tablename__ = "snmp_identity"

    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), primary_key=True)
    sys_name: Mapped[str | None] = mapped_column(String(255))
    sys_descr: Mapped[str | None] = mapped_column(Text)
    sys_object_id: Mapped[str | None] = mapped_column(String(255))
    uptime_s: Mapped[int | None] = mapped_column(BigInteger)
    last_poll_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(255))

class Interface(Base):
    __tablename__ = "interfaces"
    __table_args__ = (UniqueConstraint("device_id", "if_index", name="uq_interface_device_index"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"))
    if_index: Mapped[int] = mapped_column(Integer)
    name: Mapped[str | None] = mapped_column(String(100))
    descr: Mapped[str | None] = mapped_column(String(255))
    speed_bps: Mapped[int | None] = mapped_column(BigInteger)
    admin_status: Mapped[str | None] = mapped_column(String(20))
    oper_status: Mapped[str | None] = mapped_column(String(20))
    monitored: Mapped[bool] = mapped_column(Boolean, default=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class InterfaceSample(Base):
    __tablename__ = "interface_samples"
    __table_args__ = (Index("ix_interface_samples_if_time", "interface_id", "sampled_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    interface_id: Mapped[int] = mapped_column(ForeignKey("interfaces.id"))
    sampled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    in_octets: Mapped[int | None] = mapped_column(BigInteger)
    out_octets: Mapped[int | None] = mapped_column(BigInteger)
    in_bps: Mapped[float | None] = mapped_column(Float)
    out_bps: Mapped[float | None] = mapped_column(Float)
    oper_status: Mapped[str | None] = mapped_column(String(20))

class DeviceMetric(Base):
    """Métricas de recursos del equipo (CPU y memoria)."""
    __tablename__ = "device_metrics"
    __table_args__ = (Index("ix_device_metrics_dev_time", "device_id", "sampled_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"))
    sampled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    cpu_pct: Mapped[float | None] = mapped_column(Float)
    mem_total: Mapped[int | None] = mapped_column(BigInteger)
    mem_used: Mapped[int | None] = mapped_column(BigInteger)
    mem_pct: Mapped[float | None] = mapped_column(Float)
