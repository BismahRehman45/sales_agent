import uuid
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, Text, Float, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ProjectBant(Base):
    __tablename__ = "project_bant"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True
    )

    # Budget
    budget: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Authority
    authority: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Need
    need: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Timeline
    timeline: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Overall summary
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )
