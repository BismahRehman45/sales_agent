"""
Project Schemas

Pydantic models for project API requests and responses.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ProjectResponse(BaseModel):
    """Response schema for project list."""
    id: UUID
    name: str
    sender_email: str
    type: str
    type_confidence: float
    status: str
    document_count: int
    last_email_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ProjectDetailResponse(ProjectResponse):
    """Response schema for project detail."""
    rag: str
    type_reasoning: str | None
    updated_at: datetime


class ProjectUpdateRequest(BaseModel):
    """Request schema for updating project."""
    name: str | None = None
    status: str | None = None


class ProjectCloseResponse(BaseModel):
    """Response schema for closing project."""
    id: UUID
    name: str
    status: str
    message: str


class ProjectReopenResponse(BaseModel):
    """Response schema for reopening project."""
    id: UUID
    name: str
    status: str
    message: str


class ProjectDeleteResponse(BaseModel):
    """Response schema for deleting project."""
    message: str


class BantResponse(BaseModel):
    """Response schema for BANT analysis."""
    project_id: UUID
    budget: str
    authority: str
    need: str
    timeline: str
    summary: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
