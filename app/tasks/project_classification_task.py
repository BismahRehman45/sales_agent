"""
Project Classification Task

Celery task to classify project type using LLM.
"""

import logging

from celery import shared_task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.models.project import Project

logger = logging.getLogger(__name__)


@shared_task(name="classify_project_type", bind=True, max_retries=2)
def classify_project_type(self, project_id: str):
    """
    Classify project type using LLM.
    
    This task:
    1. Loads the project
    2. Calls LLM to classify as 'lead' or 'sale_opportunity'
    3. Updates project type, confidence, and reasoning
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
                # Load project
                result = await db.execute(
                    select(Project).where(Project.id == project_id)
                )
                project = result.scalar_one_or_none()

                if not project:
                    logger.error(f"Project {project_id} not found")
                    return {"status": "missing"}

                # Skip if no RAG content
                if not project.rag:
                    logger.warning(f"Project {project_id} has no RAG content, skipping classification")
                    return {"status": "skipped", "reason": "no_rag_content"}

                try:
                    # Call LLM for classification
                    from app.services.llm_service import LLMService
                    classification = await LLMService.classify_project_type(project.rag)

                    # Update project
                    project.type = classification["type"]
                    project.type_confidence = classification["confidence"]
                    project.type_reasoning = classification["reasoning"]

                    # Save to database
                    from app.repositories import project_repository
                    await project_repository.update_project(db, project)

                    logger.info(
                        f"Project {project_id} classified as {classification['type']} "
                        f"(confidence: {classification['confidence']:.2f})"
                    )

                    # Trigger BANT analysis if classified as sale_opportunity
                    if classification["type"] == "sale_opportunity":
                        try:
                            from app.tasks.bant_analysis_task import analyze_project_bant
                            analyze_project_bant.delay(project_id)
                            logger.info(f"Enqueued BANT analysis for project {project_id}")
                        except Exception as e:
                            logger.error(f"Failed to enqueue BANT analysis for project {project_id}: {e}")

                    return {
                        "project_id": project_id,
                        "type": classification["type"],
                        "confidence": classification["confidence"],
                        "reasoning": classification["reasoning"],
                    }

                except Exception as e:
                    logger.error(f"Failed to classify project {project_id}: {e}")
                    return {"status": "error", "error": str(e)}

        finally:
            await task_engine.dispose()

    return asyncio.run(_run())
