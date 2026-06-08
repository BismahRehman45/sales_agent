import asyncio
from app.core.database import async_session
from sqlalchemy import select
from app.models.document import Document
from app.services.project_service import ProjectService

async def test():
    async with async_session() as db:
        # Get a processed document with sender_email
        result = await db.execute(
            select(Document).where(
                Document.status == "processed",
                Document.sender_email.isnot(None)
            ).limit(1)
        )
        doc = result.scalar_one_or_none()
        
        if not doc:
            print("No suitable document found")
            return
        
        print(f"Testing with document: {doc.title}")
        print(f"Sender: {doc.sender_email}")
        print(f"Summary: {doc.summary[:100] if doc.summary else 'None'}...")
        
        # Run project matching
        try:
            result = await ProjectService.process_document(db, doc)
            print(f"\nResult: {result}")
        except Exception as e:
            print(f"\nError: {e}")
            import traceback
            traceback.print_exc()

asyncio.run(test())
