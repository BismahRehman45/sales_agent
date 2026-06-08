import os

import pdfplumber
from celery import shared_task
from docx import Document as DocxDocument
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.models.document import Document
from app.services.llm_service import LLMService


def _extract_text(file_path: str, file_type: str) -> str:
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    if file_type == "txt":
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    if file_type == "pdf":
        text_chunks = []
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                if page_text:
                    text_chunks.append(page_text)
        return "\n".join(text_chunks)

    if file_type == "docx":
        doc = DocxDocument(file_path)
        return "\n".join(p.text for p in doc.paragraphs if p.text)

    raise ValueError(f"Unsupported file_type: {file_type}")


@shared_task(name="process_uploaded_document", bind=True, max_retries=2)
def process_uploaded_document(self, document_id: str):
    import asyncio

    async def _run():
        # Fresh engine per task — avoids "another operation in progress" /
        # "attached to a different loop" errors from shared engine state.
        task_engine = create_async_engine(
            settings.DATABASE_URI,
            poolclass=NullPool,
        )
        TaskAsyncSession = async_sessionmaker(
            task_engine, class_=AsyncSession, expire_on_commit=False
        )
        try:
            async with TaskAsyncSession() as db:
                result = await db.execute(select(Document).where(Document.id == document_id))
                doc = result.scalar_one_or_none()
                if not doc:
                    return {"status": "missing"}

                try:
                    doc.status = "processing"
                    await db.commit()

                    content = _extract_text(doc.file_path, doc.file_type)
                    if not content.strip():
                        raise ValueError("Extracted text is empty")

                    doc.content = content
                    await db.commit()

                    summary = await LLMService.summarize_text(content)
                    doc.summary = summary
                    doc.status = "processed"
                    doc.error_message = None
                    await db.commit()

                    # If upload source, update project RAG
                    if doc.source == "upload":
                        from app.services.project_service import ProjectService
                        await ProjectService.update_upload_project_rag(db, doc)

                    return {"status": "processed", "summary_length": len(summary or "")}
                except Exception as e:
                    doc.status = "failed"
                    doc.error_message = str(e)[:1000]
                    await db.commit()
                    return {"status": "failed", "error": str(e)}
        finally:
            await task_engine.dispose()

    return asyncio.run(_run())
