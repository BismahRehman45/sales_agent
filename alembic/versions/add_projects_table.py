"""Create projects table with pgvector

Revision ID: add_projects_table
Revises: add_sender_email_to_documents
Create Date: 2026-06-03 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from pgvector.sqlalchemy import Vector


revision = 'add_projects_table'
down_revision = 'add_sender_email_to_documents'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable pgvector extension (already installed via Docker)
    # op.execute('CREATE EXTENSION IF NOT EXISTS vector')
    
    # Create projects table
    op.create_table(
        'projects',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', UUID(as_uuid=True), nullable=False),
        sa.Column('sender_email', sa.String(255), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('rag', sa.Text(), nullable=False, server_default=''),
        sa.Column('rag_embedding', Vector(384), nullable=True),
        sa.Column('type', sa.String(50), nullable=False, server_default='lead'),
        sa.Column('type_confidence', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('type_reasoning', sa.Text(), nullable=True),
        sa.Column('status', sa.String(50), nullable=False, server_default='open'),
        sa.Column('document_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_email_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('user_id', 'sender_email', 'name', name='uq_project_user_sender_name'),
    )
    
    # Create indexes
    op.create_index('idx_projects_user_sender', 'projects', ['user_id', 'sender_email'])
    op.execute('CREATE INDEX idx_projects_embedding ON projects USING ivfflat (rag_embedding vector_cosine_ops) WITH (lists = 100)')


def downgrade() -> None:
    op.drop_index('idx_projects_embedding', table_name='projects')
    op.drop_index('idx_projects_user_sender', table_name='projects')
    op.drop_table('projects')
    op.execute('DROP EXTENSION IF EXISTS vector')
