"""Create project_bant table

Revision ID: add_project_bant_table
Revises: add_project_documents_table
Create Date: 2026-06-04 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = 'add_project_bant_table'
down_revision = 'add_project_documents_table'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'project_bant',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('project_id', UUID(as_uuid=True), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('budget', sa.Text(), nullable=False, server_default=''),
        sa.Column('authority', sa.Text(), nullable=False, server_default=''),
        sa.Column('need', sa.Text(), nullable=False, server_default=''),
        sa.Column('timeline', sa.Text(), nullable=False, server_default=''),
        sa.Column('summary', sa.Text(), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('project_id', name='uq_project_bant_project'),
    )

    op.create_index('idx_project_bant_project', 'project_bant', ['project_id'])


def downgrade() -> None:
    op.drop_index('idx_project_bant_project', table_name='project_bant')
    op.drop_table('project_bant')
