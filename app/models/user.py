import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Boolean, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    username: Mapped[str | None] = mapped_column(String(100), nullable=True)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    google_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Gmail Integration
    gmail_access_token: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    gmail_refresh_token: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    gmail_token_expiry: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    gmail_history_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    
    # Scheduler Configuration
    timezone: Mapped[str] = mapped_column(String(50), default="Asia/Karachi")
    last_email_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)