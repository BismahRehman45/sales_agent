"""Enqueue classification for all projects."""
import asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core.config import settings
from app.models.project import Project
from app.tasks.project_classification_task import classify_project_type

async def main():
    engine = create_async_engine(settings.DATABASE_URI)
    async with async_sessionmaker(engine, class_=AsyncSession)() as db:
        result = await db.execute(select(Project.id, Project.name))
        projects = result.all()
        
        for project_id, name in projects:
            classify_project_type.delay(str(project_id))
            print(f"Enqueued: {name} ({project_id})")
        
        print(f"\nTotal: {len(projects)} classification tasks enqueued")

asyncio.run(main())
