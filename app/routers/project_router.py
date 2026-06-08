"""
Project Router

API endpoints for project management.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Security
from fastapi.security import HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.project_schema import (
    BantResponse,
    ProjectCloseResponse,
    ProjectDeleteResponse,
    ProjectDetailResponse,
    ProjectReopenResponse,
    ProjectResponse,
    ProjectUpdateRequest,
)
from app.services.project_service import ProjectService

router = APIRouter(
    prefix="/projects",
    tags=["Projects"],
    dependencies=[Security(HTTPBearer(auto_error=False))],
)


@router.get("", response_model=list[ProjectResponse])
async def list_projects(
    status: str = "open",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List all projects for current user.
    
    Args:
        status: Filter by status ("open", "closed", "all"). Default: "open"
    """
    projects = await ProjectService.get_user_projects(db, current_user.id, status)
    return projects


@router.get("/open", response_model=list[ProjectResponse])
async def list_open_projects(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get only open projects for current user."""
    projects = await ProjectService.get_user_projects(db, current_user.id, "open")
    return projects


@router.get("/{project_id}", response_model=ProjectDetailResponse)
async def get_project(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get project details with RAG content."""
    project = await ProjectService.get_project_by_id(db, str(project_id), current_user.id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.patch("/{project_id}", response_model=ProjectDetailResponse)
async def update_project(
    project_id: uuid.UUID,
    request: ProjectUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update project (name or status)."""
    project = await ProjectService.update_project(
        db, str(project_id), current_user.id, request.model_dump(exclude_unset=True)
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.delete("/{project_id}", response_model=ProjectDeleteResponse)
async def delete_project(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a project."""
    deleted = await ProjectService.delete_project(db, str(project_id), current_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectDeleteResponse(message="Project deleted successfully")


@router.post("/{project_id}/close", response_model=ProjectCloseResponse)
async def close_project(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Close a project (set status to 'closed')."""
    project = await ProjectService.close_project(db, str(project_id), current_user.id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectCloseResponse(
        id=project.id,
        name=project.name,
        status=project.status,
        message="Project closed",
    )


@router.post("/{project_id}/reopen", response_model=ProjectReopenResponse)
async def reopen_project(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reopen a project (set status to 'open')."""
    project = await ProjectService.reopen_project(db, str(project_id), current_user.id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectReopenResponse(
        id=project.id,
        name=project.name,
        status=project.status,
        message="Project reopened",
    )


@router.get("/{project_id}/bant", response_model=BantResponse)
async def get_project_bant(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get BANT analysis for a project."""
    # First check if project exists and belongs to user
    project = await ProjectService.get_project_by_id(db, str(project_id), current_user.id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Get BANT data
    from app.repositories import project_repository
    bant = await project_repository.get_project_bant(db, str(project_id))
    if not bant:
        raise HTTPException(status_code=404, detail="BANT analysis not yet available for this project")

    return bant
