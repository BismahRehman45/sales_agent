"""
Document Repository

Data access layer for document storage and retrieval.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document


async def create_document(db: AsyncSession, document: Document) -> Document:
    """Create a new document."""
    db.add(document)
    await db.commit()
    await db.refresh(document)
    return document


async def get_document_by_id(db: AsyncSession, document_id: str) -> Document | None:
    """Get document by ID."""
    result = await db.execute(select(Document).where(Document.id == document_id))
    return result.scalar_one_or_none()


async def get_documents_by_user(db: AsyncSession, user_id: str, limit: int = 100) -> list[Document]:
    """Get documents for a user."""
    result = await db.execute(
        select(Document).where(Document.user_id == user_id).limit(limit)
    )
    return result.scalars().all()


async def get_pending_documents(db: AsyncSession, limit: int = 100) -> list[Document]:
    """Get pending documents (awaiting processing)."""
    result = await db.execute(
        select(Document).where(Document.status == "pending").limit(limit)
    )
    return result.scalars().all()


async def update_document(db: AsyncSession, document: Document) -> Document:
    """Update a document."""
    db.add(document)
    await db.commit()
    await db.refresh(document)
    return document
