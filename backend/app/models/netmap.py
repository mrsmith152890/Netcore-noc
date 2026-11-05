from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

class MapDomain(Base):
    __tablename__ = "map_domains"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class MapDomainMap(Base):
    __tablename__ = "map_domain_maps"

    map_id: Mapped[int] = mapped_column(ForeignKey("maps.id", ondelete="CASCADE"), primary_key=True)
    domain_id: Mapped[int] = mapped_column(ForeignKey("map_domains.id", ondelete="CASCADE"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NetworkMap(Base):
    __tablename__ = "maps"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class MapNode(Base):
    """Posición de un dispositivo (o una etiqueta) dentro de un mapa."""
    __tablename__ = "map_nodes"
    __table_args__ = (
        UniqueConstraint("map_id", "device_id", name="uq_map_node_device"),
        UniqueConstraint("map_id", "child_map_id", name="uq_map_node_child"),
        UniqueConstraint("map_id", "ip_address", name="uq_map_node_ip"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    map_id: Mapped[int] = mapped_column(ForeignKey("maps.id", ondelete="CASCADE"))
    node_type: Mapped[str] = mapped_column(String(10), default="device")  # device | label
    device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id"))
    child_map_id: Mapped[int | None] = mapped_column(ForeignKey("maps.id", ondelete="CASCADE"))
    ip_address: Mapped[str | None] = mapped_column(String(45))
    discovery_source: Mapped[str | None] = mapped_column(String(20))
    last_ping_ok: Mapped[bool | None] = mapped_column(Boolean)
    last_snmp_ok: Mapped[bool | None] = mapped_column(Boolean)
    last_arp_seen: Mapped[bool | None] = mapped_column(Boolean)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    label: Mapped[str | None] = mapped_column(String(200))
    icon_data: Mapped[str | None] = mapped_column(Text)
    x: Mapped[float] = mapped_column(Float, default=0)
    y: Mapped[float] = mapped_column(Float, default=0)

class MapLink(Base):
    __tablename__ = "map_links"
    __table_args__ = (UniqueConstraint("map_id", "source_node_id", "target_node_id", name="uq_map_link"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    map_id: Mapped[int] = mapped_column(ForeignKey("maps.id", ondelete="CASCADE"))
    source_node_id: Mapped[int] = mapped_column(ForeignKey("map_nodes.id", ondelete="CASCADE"))
    target_node_id: Mapped[int] = mapped_column(ForeignKey("map_nodes.id", ondelete="CASCADE"))
    source_handle: Mapped[str | None] = mapped_column(String(10))
    target_handle: Mapped[str | None] = mapped_column(String(10))
    label: Mapped[str | None] = mapped_column(String(100))
