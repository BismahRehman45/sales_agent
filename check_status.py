import asyncio
from app.core.database import engine
from sqlalchemy import text

async def check():
    async with engine.connect() as conn:
        # Check documents
        result = await conn.execute(text("SELECT id, title, status, sender_email FROM documents LIMIT 5"))
        docs = [dict(row._mapping) for row in result]
        print("=== DOCUMENTS ===")
        for d in docs:
            print(f"  {d['title']} | status={d['status']} | sender={d['sender_email']}")
        
        # Check projects
        result = await conn.execute(text("SELECT id, name, sender_email, document_count FROM projects LIMIT 5"))
        projects = [dict(row._mapping) for row in result]
        print("\n=== PROJECTS ===")
        if not projects:
            print("  No projects found!")
        for p in projects:
            print(f"  {p['name']} | sender={p['sender_email']} | docs={p['document_count']}")
        
        # Check Celery tasks
        result = await conn.execute(text("SELECT COUNT(*) FROM documents WHERE status='processed'"))
        processed = result.fetchone()[0]
        print(f"\n=== STATS ===")
        print(f"  Processed documents: {processed}")

asyncio.run(check())
