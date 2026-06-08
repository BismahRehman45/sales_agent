import asyncio
from app.core.database import async_session
from sqlalchemy import select
from app.models.document import Document
from app.services.project_service import ProjectService

async def process_all():
    async with async_session() as db:
        # Get all processed documents with sender_email
        result = await db.execute(
            select(Document).where(
                Document.status == "processed",
                Document.sender_email.isnot(None)
            )
        )
        docs = result.scalars().all()
        
        print(f"Found {len(docs)} documents to process")
        
        success = 0
        errors = 0
        for doc in docs:
            try:
                result = await ProjectService.process_document(db, doc)
                if result.get("status") == "success":
                    success += 1
                    print(f"  OK: {doc.title[:40]} -> {result.get('action')}")
                else:
                    print(f"  SKIP: {doc.title[:40]} -> {result.get('reason')}")
            except Exception as e:
                errors += 1
                print(f"  ERROR: {doc.title[:40]} -> {str(e)[:50]}")
        
        print(f"\nDone: {success} created/updated, {errors} errors")

asyncio.run(process_all())
