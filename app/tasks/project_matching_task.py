"""
Project Matching Task

Celery task to process documents through RAG pipeline.
"""

import logging

from celery import shared_task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.models.document import Document

logger = logging.getLogger(__name__)


@shared_task(name="match_document_to_project", bind=True, max_retries=2)
def match_document_to_project(self, document_id: str):
    """
    Process document through RAG pipeline.
    
    This task:
    1. Loads the document
    2. Computes embedding of summary
    3. Searches for matching project
    4. Updates or creates project
    5. Links document to project
    """
    import asyncio

    async def _run():
        # Fresh engine per task
        task_engine = create_async_engine(
            settings.DATABASE_URI,
            poolclass=NullPool,
        )
        TaskAsyncSession = async_sessionmaker(
            task_engine, class_=AsyncSession, expire_on_commit=False
        )
        try:
            async with TaskAsyncSession() as db:
                # Load document
                result = await db.execute(
                    select(Document).where(Document.id == document_id)
                )
                doc = result.scalar_one_or_none()

                if not doc:
                    logger.error(f"Document {document_id} not found")
                    return {"status": "missing"}

                # Process through RAG pipeline
                from app.services.project_service import ProjectService
                result = await ProjectService.process_document(db, doc)
                
                logger.info(f"Project matching completed for document {document_id}: {result}")
                return result

        finally:
            await task_engine.dispose()

    return asyncio.run(_run())
