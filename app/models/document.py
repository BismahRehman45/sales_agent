import uuid
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    source: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g., "gmail", "upload"
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)  # Email subject or file name
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")  # Extracted text
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)  # LLM-generated summary
    file_type: Mapped[str | None] = mapped_column(String(50), nullable=True)  # e.g., "email", "pdf", "docx", "txt"
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)  # Disk path for uploaded files
    status: Mapped[str] = mapped_column(
        String(50), default="pending"
    )  # pending, processing, processed, failed
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    sender_email: Mapped[str | None] = mapped_column(String(255), nullable=True)  # NULL for uploads
