"""Add file_path to documents and make content default empty

Revision ID: add_document_file_path
Revises: add_gmail_scheduler_fields
Create Date: 2026-06-02 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'add_document_file_path'
down_revision = 'add_gmail_scheduler_fields'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('documents', sa.Column('file_path', sa.String(500), nullable=True))
    op.alter_column('documents', 'content', nullable=True, server_default='')


def downgrade() -> None:
    op.alter_column('documents', 'content', nullable=False, server_default=None)
    op.drop_column('documents', 'file_path')
