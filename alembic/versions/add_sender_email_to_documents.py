"""Add sender_email to documents

Revision ID: add_sender_email_to_documents
Revises: add_document_file_path
Create Date: 2026-06-03 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'add_sender_email_to_documents'
down_revision = 'add_document_file_path'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('documents', sa.Column('sender_email', sa.String(255), nullable=True))
    op.create_index('idx_documents_user_sender', 'documents', ['user_id', 'sender_email'], postgresql_where='sender_email IS NOT NULL')


def downgrade() -> None:
    op.drop_index('idx_documents_user_sender', table_name='documents')
    op.drop_column('documents', 'sender_email')
