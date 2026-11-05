from datetime import datetime
from sqlalchemy import Boolean, DateTime, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class AppBranding(Base):
    __tablename__ = "app_branding"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    logo_data: Mapped[str | None] = mapped_column(Text)
    favicon_data: Mapped[str | None] = mapped_column(Text)
    login_art_data: Mapped[str | None] = mapped_column(Text)
    login_status_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
