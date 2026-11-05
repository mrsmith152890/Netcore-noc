from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

class DiscoveryScope(Base):
    """Rango CIDR autorizado para escanear en una sede."""
    __tablename__ = "discovery_scopes"
    __table_args__ = (UniqueConstraint("site_id", "cidr", name="uq_scope_site_cidr"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id"))
    cidr: Mapped[str] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(String(255))
    community_enc: Mapped[str | None] = mapped_column(Text)
    snmp_port: Mapped[int] = mapped_column(Integer, default=161)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    allow_public: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class DiscoveryRun(Base):
    __tablename__ = "discovery_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    scope_id: Mapped[int] = mapped_column(ForeignKey("discovery_scopes.id"))
    status: Mapped[str] = mapped_column(String(12), default="pending")  # pending|running|done|failed|cancelled
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    hosts_total: Mapped[int] = mapped_column(Integer, default=0)
    hosts_scanned: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    hosts_alive: Mapped[int] = mapped_column(Integer, default=0)
    hosts_snmp: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(String(255))

class DiscoveredHost(Base):
    __tablename__ = "discovered_hosts"
    __table_args__ = (UniqueConstraint("run_id", "ip", name="uq_run_ip"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("discovery_runs.id", ondelete="CASCADE"))
    ip: Mapped[str] = mapped_column(String(45))
    rtt_ms: Mapped[float | None] = mapped_column(Float)
    snmp_ok: Mapped[bool] = mapped_column(Boolean, default=False)
    sys_name: Mapped[str | None] = mapped_column(String(255))
    sys_descr: Mapped[str | None] = mapped_column(Text)
    sys_object_id: Mapped[str | None] = mapped_column(String(255))
    vendor: Mapped[str | None] = mapped_column(String(50))
    device_type: Mapped[str] = mapped_column(String(30), default="other")
    device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id"))
    status: Mapped[str] = mapped_column(String(20), default="new")  # new | registered | imported
