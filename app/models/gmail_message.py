import uuid
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, Text, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class GmailMessage(Base):
    __tablename__ = "gmail_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    gmail_message_id: Mapped[str] = mapped_column(
        String(255), nullable=False
    )  # Gmail's unique message ID
    subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sender: Mapped[str | None] = mapped_column(String(255), nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    status: Mapped[str] = mapped_column(
        String(50), default="pending"
    )  # pending, processed, failed
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )  # Reference to created Document

    __table_args__ = (
        UniqueConstraint(
            "user_id", "gmail_message_id", name="uq_user_gmail_message"
        ),  # Prevent duplicates per user
        Index("idx_user_synced", "user_id", "synced_at"),  # Optimize pagination queries
    )
