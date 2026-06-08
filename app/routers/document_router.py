import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Security, UploadFile
from fastapi.security import HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_user
from app.models.user import User
from app.core.database import get_db
from app.repositories import document_repository
from app.schemas.document_schema import (
    DocumentDetailResponse,
    DocumentResponse,
    DocumentUploadResponse,
)
from app.services.document_service import save_uploaded_file

router = APIRouter(
    prefix="/documents",
    tags=["Documents"],
    dependencies=[Security(HTTPBearer(auto_error=False))],
)


@router.post("/upload", response_model=DocumentUploadResponse, status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    project_id: uuid.UUID = Form(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    document = await save_uploaded_file(db, current_user, file, project_id)
    return DocumentUploadResponse(
        id=document.id,
        title=document.title,
        file_type=document.file_type,
        status=document.status,
        message="File uploaded. Celery task queued for processing.",
    )


@router.get("", response_model=list[DocumentResponse])
async def list_documents(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    docs = await document_repository.get_documents_by_user(db, current_user.id)
    return docs


@router.get("/{document_id}", response_model=DocumentDetailResponse)
async def get_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    doc = await document_repository.get_document_by_id(db, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your document")
    return doc
