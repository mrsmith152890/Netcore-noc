from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

class Device(Base):
    __tablename__ = "devices"
    __table_args__ = (UniqueConstraint("site_id", "ip_address", name="uq_device_site_ip"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id"))
    name: Mapped[str] = mapped_column(String(100))
    ip_address: Mapped[str] = mapped_column(String(45))
    device_type: Mapped[str] = mapped_column(String(30), default="other")  # router, switch, firewall, server, ap, other
    vendor: Mapped[str | None] = mapped_column(String(50))
    model: Mapped[str | None] = mapped_column(String(80))
    wan_gateway_ip: Mapped[str | None] = mapped_column(String(45))
    wan_probe_ip: Mapped[str | None] = mapped_column(String(45))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)  # estado administrativo
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    site: Mapped["Site"] = relationship(back_populates="devices")
