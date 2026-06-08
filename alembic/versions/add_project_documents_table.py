"""Create project_documents junction table

Revision ID: add_project_documents_table
Revises: add_projects_table
Create Date: 2026-06-03 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = 'add_project_documents_table'
down_revision = 'add_projects_table'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'project_documents',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('project_id', UUID(as_uuid=True), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('document_id', UUID(as_uuid=True), sa.ForeignKey('documents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('added_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('project_id', 'document_id', name='uq_project_document'),
    )
    
    op.create_index('idx_project_documents_project', 'project_documents', ['project_id'])
    op.create_index('idx_project_documents_document', 'project_documents', ['document_id'])


def downgrade() -> None:
    op.drop_index('idx_project_documents_document', table_name='project_documents')
    op.drop_index('idx_project_documents_project', table_name='project_documents')
    op.drop_table('project_documents')
