import asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core.config import settings
from app.models.project import Project

async def main():
    engine = create_async_engine(settings.DATABASE_URI)
    async with async_sessionmaker(engine, class_=AsyncSession)() as db:
        result = await db.execute(select(Project))
        projects = result.scalars().all()
        for p in projects:
            print(f"ID: {p.id}")
            print(f"  Name: {p.name}")
            print(f"  Sender: {p.sender_email}")
            print(f"  Type: {p.type} (confidence: {p.type_confidence})")
            print(f"  Docs: {p.document_count}")
            print(f"  Status: {p.status}")
            print(f"  RAG length: {len(p.rag) if p.rag else 0} chars")
            print()

asyncio.run(main())
