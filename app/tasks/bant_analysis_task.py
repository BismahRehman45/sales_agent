"""
BANT Analysis Task

Celery task to analyze BANT (Budget, Authority, Need, Timeline) for projects.
"""

import logging

from celery import shared_task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.models.project import Project

logger = logging.getLogger(__name__)


@shared_task(name="analyze_project_bant", bind=True, max_retries=2)
def analyze_project_bant(self, project_id: str):
    """
    Analyze BANT for a project classified as sale_opportunity.
    
    This task:
    1. Loads the project
    2. Calls LLM to analyze Budget, Authority, Need, Timeline
    3. Creates/updates ProjectBant record
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
                    logger.warning(f"Project {project_id} has no RAG content, skipping BANT analysis")
                    return {"status": "skipped", "reason": "no_rag_content"}

                # Skip if not sale_opportunity
                if project.type != "sale_opportunity":
                    logger.info(f"Project {project_id} is {project.type}, not sale_opportunity, skipping BANT")
                    return {"status": "skipped", "reason": "not_sale_opportunity"}

                try:
                    # Call LLM for BANT analysis
                    from app.services.llm_service import LLMService
                    bant_result = await LLMService.analyze_bant(project.rag)

                    # Create or update ProjectBant record
                    from app.models.project_bant import ProjectBant
                    from app.repositories import project_repository

                    project_bant = ProjectBant(
                        project_id=project.id,
                        budget=bant_result["budget"],
                        authority=bant_result["authority"],
                        need=bant_result["need"],
                        timeline=bant_result["timeline"],
                        summary=bant_result["summary"],
                    )

                    await project_repository.create_or_update_project_bant(db, project_bant)

                    logger.info(f"BANT analysis completed for project {project_id}")

                    return {
                        "project_id": project_id,
                        "status": "completed",
                    }

                except Exception as e:
                    logger.error(f"Failed to analyze BANT for project {project_id}: {e}")
                    return {"status": "error", "error": str(e)}

        finally:
            await task_engine.dispose()

    return asyncio.run(_run())
