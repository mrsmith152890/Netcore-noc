from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

class NotificationChannel(Base):
    __tablename__ = "notification_channels"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    type: Mapped[str] = mapped_column(String(20), default="telegram")
    config_enc: Mapped[str] = mapped_column(Text)  # JSON cifrado (token, chat_id)
    min_severity: Mapped[str] = mapped_column(String(10), default="warning")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class AlertRule(Base):
    __tablename__ = "alert_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    rule_type: Mapped[str] = mapped_column(String(20))  # device_down | cpu_high | mem_high | latency_high
    threshold: Mapped[float | None] = mapped_column(Float)
    for_seconds: Mapped[int] = mapped_column(Integer, default=0)
    recover_after_s: Mapped[int] = mapped_column(Integer, default=60)
    severity: Mapped[str] = mapped_column(String(10), default="warning")
    site_id: Mapped[int | None] = mapped_column(ForeignKey("sites.id"))
    device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id"))
    check_type: Mapped[str | None] = mapped_column(String(10))  # tcp | http | dns (solo service_down)
    repeat_interval_s: Mapped[int] = mapped_column(Integer, default=3600)  # 0 = sin recordatorios
    escalate_after_s: Mapped[int | None] = mapped_column(Integer)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        # una sola alerta no resuelta por (regla, dispositivo)
        Index("uq_active_alert", "rule_id", "device_id", unique=True,
              postgresql_where=text("state <> 'resolved'")),
        Index("ix_alerts_state", "state"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("alert_rules.id"))
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"))
    state: Mapped[str] = mapped_column(String(12), default="pending")  # pending|firing|acknowledged|resolved
    severity: Mapped[str] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ack_note: Mapped[str | None] = mapped_column(String(255))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution: Mapped[str | None] = mapped_column(String(30))  # recuperada | auto-cerrada
    clear_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_value: Mapped[float | None] = mapped_column(Float)
    last_detail: Mapped[str | None] = mapped_column(String(255))
    last_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    escalated: Mapped[bool] = mapped_column(Boolean, default=False)

class Silence(Base):
    __tablename__ = "alert_silences"

    id: Mapped[int] = mapped_column(primary_key=True)
    rule_id: Mapped[int | None] = mapped_column(ForeignKey("alert_rules.id"))
    device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id"))
    site_id: Mapped[int | None] = mapped_column(ForeignKey("sites.id"))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class Notification(Base):
    """Cola de salida: el evaluador escribe aquí y el worker envía con reintentos."""
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_pending", "status", "next_attempt_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    alert_id: Mapped[int | None] = mapped_column(ForeignKey("alerts.id"))
    channel_id: Mapped[int] = mapped_column(ForeignKey("notification_channels.id"))
    kind: Mapped[str] = mapped_column(String(12))  # firing|reminder|escalated|recovered|test
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(12), default="pending")  # pending|sent|failed|suppressed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(255))
