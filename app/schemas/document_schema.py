import uuid
from datetime import datetime

from pydantic import BaseModel


class DocumentUploadResponse(BaseModel):
    id: uuid.UUID
    title: str | None
    file_type: str | None
    status: str
    message: str


class DocumentResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    source: str
    title: str | None
    file_type: str | None
    status: str
    summary: str | None
    error_message: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentDetailResponse(DocumentResponse):
    content: str | None
