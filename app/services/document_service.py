import os
import uuid
from pathlib import Path

import aiofiles
from fastapi import HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.project_document import ProjectDocument
from app.models.user import User
from app.repositories import document_repository, project_repository

ALLOWED_EXTENSIONS = {"txt", "pdf", "docx"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
UPLOAD_DIR = Path("uploads")


def _get_extension(filename: str) -> str:
    if "." not in filename:
        raise HTTPException(status_code=400, detail="File has no extension")
    return filename.rsplit(".", 1)[1].lower()


async def save_uploaded_file(
    db: AsyncSession,
    user: User,
    upload_file: UploadFile,
    project_id: uuid.UUID,
) -> Document:
    if not upload_file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    ext = _get_extension(upload_file.filename)
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: .{ext}. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    contents = await upload_file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="File is empty")
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Max {MAX_FILE_SIZE // (1024 * 1024)} MB",
        )

    user_dir = UPLOAD_DIR / str(user.id)
    user_dir.mkdir(parents=True, exist_ok=True)

    doc_id = uuid.uuid4()
    saved_path = user_dir / f"{doc_id}.{ext}"

    async with aiofiles.open(saved_path, "wb") as f:
        await f.write(contents)

    document = Document(
        id=doc_id,
        user_id=user.id,
        source="upload",
        title=upload_file.filename,
        content="",
        file_type=ext,
        file_path=str(saved_path),
        status="pending",
    )
    document = await document_repository.create_document(db, document)

    # Validate project exists and belongs to user
    project = await project_repository.get_project_by_id(db, str(project_id))
    if not project or str(project.user_id) != str(user.id):
        raise HTTPException(status_code=404, detail="Project not found")

    # Create link in project_documents table
    project_doc = ProjectDocument(
        project_id=project_id,
        document_id=document.id,
    )
    await project_repository.create_project_document(db, project_doc)

    from app.tasks.document_processing_task import process_uploaded_document
    process_uploaded_document.delay(str(document.id))

    return document
