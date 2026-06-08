"""
Project Service

Main service for project matching and RAG management.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.document import Document
from app.models.project import Project
from app.models.project_document import ProjectDocument
from app.repositories import project_repository
from app.services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


class ProjectService:
    """Service for managing projects with RAG matching."""

    @staticmethod
    async def process_document(db: AsyncSession, document: Document) -> dict:
        """
        Process document through RAG pipeline.
        
        Flow:
        1. Check if document has sender_email
        2. Compute embedding of document summary
        3. Search for matching project (user_id + sender_email + status='open')
        4. If match found (similarity >= threshold): update project RAG
        5. If no match: create new project
        6. Link document to project
        7. Trigger type classification (async)
        
        Args:
            db: Database session
            document: Document to process
            
        Returns:
            dict with processing results
        """
        # Skip if no sender_email (uploads)
        if not document.sender_email:
            logger.info(f"Document {document.id} has no sender_email, skipping project matching")
            return {"status": "skipped", "reason": "no_sender_email"}

        # Skip if no summary
        if not document.summary:
            logger.warning(f"Document {document.id} has no summary, skipping project matching")
            return {"status": "skipped", "reason": "no_summary"}

        try:
            # Step 1: Compute embedding of document summary
            summary_embedding = EmbeddingService.compute_embedding(document.summary)
            logger.debug(f"Computed embedding for document {document.id}")

            # Step 2: Search for matching project
            best_project = await ProjectService._find_matching_project(
                db, document.user_id, document.sender_email, summary_embedding
            )

            # Step 3: Update or create project
            if best_project:
                # Update existing project
                project = await ProjectService._update_project_rag(
                    db, best_project, document
                )
                action = "updated"
                logger.info(f"Document {document.id} added to existing project {project.id}")
            else:
                # Create new project
                project = await ProjectService._create_new_project(
                    db, document, summary_embedding
                )
                action = "created"
                logger.info(f"Document {document.id} created new project {project.id}")

            # Step 4: Link document to project via junction table
            await ProjectService._link_document_to_project(db, project.id, document.id)

            # Step 5: Trigger type classification (async)
            try:
                from app.tasks.project_classification_task import classify_project_type
                classify_project_type.delay(str(project.id))
            except Exception as e:
                logger.error(f"Failed to enqueue type classification for project {project.id}: {e}")

            return {
                "status": "success",
                "action": action,
                "project_id": str(project.id),
                "project_name": project.name,
                "similarity": best_project.get("similarity") if best_project else None,
            }

        except Exception as e:
            doc_id = str(document.id) if hasattr(document, 'id') else "unknown"
            logger.error(f"Error processing document {doc_id} for project matching: {e}")
            return {"status": "error", "error": str(e)}

    @staticmethod
    async def _find_matching_project(
        db: AsyncSession,
        user_id: str,
        sender_email: str,
        query_embedding: list[float],
    ) -> dict | None:
        """
        Find best matching project using pgvector cosine similarity.
        
        Args:
            db: Database session
            user_id: User ID
            sender_email: Sender email
            query_embedding: Embedding to compare against
            
        Returns:
            dict with project info and similarity, or None if no match
        """
        emb_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

        query = text("""
            SELECT 
                p.id,
                p.name,
                p.rag,
                p.type,
                p.status,
                1 - (p.rag_embedding <=> CAST(:emb AS vector)) as similarity
            FROM projects p
            WHERE p.user_id = :user_id
              AND p.sender_email = :sender_email
              AND p.status = 'open'
              AND p.rag_embedding IS NOT NULL
            ORDER BY p.rag_embedding <=> CAST(:emb AS vector)
            LIMIT 1
        """)

        result = await db.execute(query, {
            "emb": emb_str,
            "user_id": user_id,
            "sender_email": sender_email,
        })

        row = result.fetchone()

        if row and row.similarity >= settings.PROJECT_MATCH_THRESHOLD:
            return {
                "id": row.id,
                "name": row.name,
                "rag": row.rag,
                "type": row.type,
                "status": row.status,
                "similarity": float(row.similarity),
            }

        return None

    @staticmethod
    async def _create_new_project(
        db: AsyncSession,
        document: Document,
        summary_embedding: list[float],
    ) -> Project:
        """
        Create a new project with initial RAG content.
        
        Args:
            db: Database session
            document: Document to create project from
            summary_embedding: Embedding of document summary
            
        Returns:
            Created Project
        """
        # Generate project name using LLM
        from app.services.llm_service import LLMService
        name = await LLMService.generate_project_name(document.summary)

        # Check for name uniqueness
        existing = await project_repository.get_project_by_user_sender_name(
            db, document.user_id, document.sender_email, name
        )
        if existing:
            # Append timestamp to make unique
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
            name = f"{name} ({timestamp})"

        # Create project with initial RAG = document content
        project = Project(
            user_id=document.user_id,
            sender_email=document.sender_email,
            name=name,
            rag=document.content or document.summary,
            rag_embedding=summary_embedding,
            document_count=1,
            last_email_at=datetime.now(timezone.utc),
        )

        return await project_repository.create_project(db, project)

    @staticmethod
    async def _update_project_rag(
        db: AsyncSession,
        project_info: dict,
        document: Document,
    ) -> Project:
        """
        Update existing project RAG with new document content.
        
        Args:
            db: Database session
            project_info: Project info dict from search
            document: Document to add
            
        Returns:
            Updated Project
        """
        # Load full project from database
        project = await project_repository.get_project_by_id(db, project_info["id"])
        if not project:
            raise ValueError(f"Project {project_info['id']} not found")

        # Append new content to RAG
        separator = "\n\n---\n\n"
        new_content = document.content or document.summary
        project.rag = project.rag + separator + new_content

        # Re-embed full RAG
        project.rag_embedding = EmbeddingService.compute_embedding(project.rag)

        # Update metadata
        project.document_count += 1
        project.last_email_at = datetime.now(timezone.utc)

        updated_project = await project_repository.update_project(db, project)

        # Re-run BANT analysis if project is sale_opportunity
        if updated_project.type == "sale_opportunity":
            try:
                from app.tasks.bant_analysis_task import analyze_project_bant
                analyze_project_bant.delay(str(updated_project.id))
                logger.info(f"Enqueued BANT re-analysis for project {updated_project.id}")
            except Exception as e:
                logger.error(f"Failed to enqueue BANT re-analysis for project {updated_project.id}: {e}")

        return updated_project

    @staticmethod
    async def _link_document_to_project(
        db: AsyncSession,
        project_id: str,
        document_id: str,
    ) -> ProjectDocument | None:
        """
        Link document to project via junction table.
        
        Args:
            db: Database session
            project_id: Project ID
            document_id: Document ID
            
        Returns:
            Created ProjectDocument or None if already linked
        """
        # Check if link already exists
        existing = await db.execute(
            select(ProjectDocument).where(
                ProjectDocument.project_id == project_id,
                ProjectDocument.document_id == document_id
            )
        )
        if existing.scalar_one_or_none():
            return None
        
        project_doc = ProjectDocument(
            project_id=project_id,
            document_id=document_id,
        )
        return await project_repository.create_project_document(db, project_doc)

    @staticmethod
    async def update_upload_project_rag(
        db: AsyncSession,
        document: Document,
    ) -> dict:
        """
        Update project RAG for uploaded document.
        Finds project via project_documents table, appends content, re-embeds.
        """
        # Find project_id from project_documents table
        result = await db.execute(
            select(ProjectDocument).where(ProjectDocument.document_id == document.id)
        )
        project_doc = result.scalar_one_or_none()

        if not project_doc:
            logger.warning(f"Document {document.id} has no project link")
            return {"status": "skipped", "reason": "no_project_link"}

        # Load project
        project = await project_repository.get_project_by_id(db, str(project_doc.project_id))
        if not project:
            logger.error(f"Project {project_doc.project_id} not found")
            return {"status": "error", "reason": "project_not_found"}

        # Append content to RAG
        separator = "\n\n---\n\n"
        new_content = document.content or document.summary
        project.rag = project.rag + separator + new_content

        # Re-embed full RAG
        project.rag_embedding = EmbeddingService.compute_embedding(project.rag)

        # Update document_count only, NOT last_email_at
        project.document_count += 1

        updated_project = await project_repository.update_project(db, project)

        # Re-run BANT analysis if project is sale_opportunity
        if updated_project.type == "sale_opportunity":
            try:
                from app.tasks.bant_analysis_task import analyze_project_bant
                analyze_project_bant.delay(str(updated_project.id))
                logger.info(f"Enqueued BANT re-analysis for project {updated_project.id}")
            except Exception as e:
                logger.error(f"Failed to enqueue BANT re-analysis for project {updated_project.id}: {e}")

        logger.info(f"Uploaded document {document.id} added to project {updated_project.id}")

        return {
            "status": "success",
            "project_id": str(updated_project.id),
            "project_name": updated_project.name,
        }

    @staticmethod
    async def get_user_projects(
        db: AsyncSession,
        user_id: str,
        status: str = "open",
    ) -> list[Project]:
        """
        Get all projects for a user.
        
        Args:
            db: Database session
            user_id: User ID
            status: Filter by status ("open", "closed", "all")
            
        Returns:
            List of projects
        """
        return await project_repository.get_projects_by_user(db, user_id, status)

    @staticmethod
    async def get_project_by_id(
        db: AsyncSession,
        project_id: str,
        user_id: str,
    ) -> Project | None:
        """
        Get project by ID with user ownership check.
        
        Args:
            db: Database session
            project_id: Project ID
            user_id: User ID for ownership check
            
        Returns:
            Project or None
        """
        project = await project_repository.get_project_by_id(db, project_id)
        if project and str(project.user_id) == str(user_id):
            return project
        return None

    @staticmethod
    async def close_project(
        db: AsyncSession,
        project_id: str,
        user_id: str,
    ) -> Project | None:
        """
        Close a project (set status to 'closed').
        
        Args:
            db: Database session
            project_id: Project ID
            user_id: User ID for ownership check
            
        Returns:
            Updated Project or None
        """
        project = await project_repository.get_project_by_id(db, project_id)
        if not project or str(project.user_id) != str(user_id):
            return None

        project.status = "closed"
        return await project_repository.update_project(db, project)

    @staticmethod
    async def reopen_project(
        db: AsyncSession,
        project_id: str,
        user_id: str,
    ) -> Project | None:
        """
        Reopen a project (set status to 'open').
        
        Args:
            db: Database session
            project_id: Project ID
            user_id: User ID for ownership check
            
        Returns:
            Updated Project or None
        """
        project = await project_repository.get_project_by_id(db, project_id)
        if not project or str(project.user_id) != str(user_id):
            return None

        project.status = "open"
        return await project_repository.update_project(db, project)

    @staticmethod
    async def update_project(
        db: AsyncSession,
        project_id: str,
        user_id: str,
        update_data: dict,
    ) -> Project | None:
        """
        Update project fields.
        
        Args:
            db: Database session
            project_id: Project ID
            user_id: User ID for ownership check
            update_data: Dict of fields to update
            
        Returns:
            Updated Project or None
        """
        project = await project_repository.get_project_by_id(db, project_id)
        if not project or str(project.user_id) != str(user_id):
            return None

        if "name" in update_data and update_data["name"] is not None:
            project.name = update_data["name"]
        if "status" in update_data and update_data["status"] is not None:
            project.status = update_data["status"]

        return await project_repository.update_project(db, project)

    @staticmethod
    async def delete_project(
        db: AsyncSession,
        project_id: str,
        user_id: str,
    ) -> bool:
        """
        Delete a project.
        
        Args:
            db: Database session
            project_id: Project ID
            user_id: User ID for ownership check
            
        Returns:
            True if deleted, False if not found or not owned
        """
        project = await project_repository.get_project_by_id(db, project_id)
        if not project or str(project.user_id) != str(user_id):
            return False

        await project_repository.delete_project(db, project)
        return True
