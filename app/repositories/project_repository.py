"""
Project Repository

Data access layer for project storage and retrieval.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.project_document import ProjectDocument
from app.models.project_bant import ProjectBant


async def create_project(db: AsyncSession, project: Project) -> Project:
    """Create a new project."""
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


async def get_project_by_id(db: AsyncSession, project_id: str) -> Project | None:
    """Get project by ID."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    return result.scalar_one_or_none()


async def get_projects_by_user(db: AsyncSession, user_id: str, status: str = "open") -> list[Project]:
    """Get projects for a user, optionally filtered by status."""
    query = select(Project).where(Project.user_id == user_id)
    if status != "all":
        query = query.where(Project.status == status)
    result = await db.execute(query.order_by(Project.updated_at.desc()))
    return result.scalars().all()


async def get_projects_by_user_sender(
    db: AsyncSession, user_id: str, sender_email: str, status: str = "open"
) -> list[Project]:
    """Get projects for a user and sender, optionally filtered by status."""
    query = select(Project).where(
        Project.user_id == user_id,
        Project.sender_email == sender_email,
    )
    if status != "all":
        query = query.where(Project.status == status)
    result = await db.execute(query)
    return result.scalars().all()


async def update_project(db: AsyncSession, project: Project) -> Project:
    """Update a project."""
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


async def delete_project(db: AsyncSession, project: Project) -> None:
    """Delete a project."""
    await db.delete(project)
    await db.commit()


async def create_project_document(db: AsyncSession, project_document: ProjectDocument) -> ProjectDocument:
    """Create a project-document link."""
    db.add(project_document)
    await db.commit()
    await db.refresh(project_document)
    return project_document


async def get_documents_by_project(db: AsyncSession, project_id: str) -> list[ProjectDocument]:
    """Get all document links for a project."""
    result = await db.execute(
        select(ProjectDocument).where(ProjectDocument.project_id == project_id)
    )
    return result.scalars().all()


async def get_project_by_user_sender_name(
    db: AsyncSession, user_id: str, sender_email: str, name: str
) -> Project | None:
    """Get project by user, sender, and name (for uniqueness check)."""
    result = await db.execute(
        select(Project).where(
            Project.user_id == user_id,
            Project.sender_email == sender_email,
            Project.name == name,
        )
    )
    return result.scalar_one_or_none()


async def create_or_update_project_bant(db: AsyncSession, project_bant: ProjectBant) -> ProjectBant:
    """Create or update a project BANT record."""
    # Check if BANT exists for this project
    existing = await get_project_bant(db, str(project_bant.project_id))
    if existing:
        # Update existing
        existing.budget = project_bant.budget
        existing.authority = project_bant.authority
        existing.need = project_bant.need
        existing.timeline = project_bant.timeline
        existing.summary = project_bant.summary
        db.add(existing)
        await db.commit()
        await db.refresh(existing)
        return existing
    else:
        # Create new
        db.add(project_bant)
        await db.commit()
        await db.refresh(project_bant)
        return project_bant


async def get_project_bant(db: AsyncSession, project_id: str) -> ProjectBant | None:
    """Get BANT record for a project."""
    result = await db.execute(
        select(ProjectBant).where(ProjectBant.project_id == project_id)
    )
    return result.scalar_one_or_none()


async def delete_project_bant(db: AsyncSession, project_id: str) -> None:
    """Delete BANT record for a project."""
    bant = await get_project_bant(db, project_id)
    if bant:
        await db.delete(bant)
        await db.commit()
