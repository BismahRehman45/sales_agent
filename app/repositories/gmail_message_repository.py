"""
Gmail Message Repository

Data access layer for Gmail message deduplication and tracking.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.gmail_message import GmailMessage


async def get_message_by_gmail_id(
    db: AsyncSession, user_id: str, gmail_message_id: str
) -> GmailMessage | None:
    """Check if Gmail message already exists for this user."""
    result = await db.execute(
        select(GmailMessage).where(
            (GmailMessage.user_id == user_id)
            & (GmailMessage.gmail_message_id == gmail_message_id)
        )
    )
    return result.scalar_one_or_none()


async def create_message(db: AsyncSession, message: GmailMessage) -> GmailMessage:
    """Create a new Gmail message record."""
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return message


async def update_message(db: AsyncSession, message: GmailMessage) -> GmailMessage:
    """Update an existing Gmail message record."""
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return message


async def get_unprocessed_messages(
    db: AsyncSession, user_id: str, limit: int = 100
) -> list[GmailMessage]:
    """Get unprocessed Gmail messages for a user."""
    result = await db.execute(
        select(GmailMessage)
        .where((GmailMessage.user_id == user_id) & (GmailMessage.status == "pending"))
        .limit(limit)
    )
    return result.scalars().all()
