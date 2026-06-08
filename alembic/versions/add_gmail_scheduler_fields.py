"""Add gmail fields, timezone, and create documents and gmail_messages tables

Revision ID: add_gmail_scheduler_fields
Revises: create_token_blacklist
Create Date: 2026-06-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_gmail_scheduler_fields'
down_revision = 'create_token_blacklist'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add Gmail and timezone fields to users table
    op.add_column('users', sa.Column('gmail_access_token', sa.String(1000), nullable=True))
    op.add_column('users', sa.Column('gmail_refresh_token', sa.String(1000), nullable=True))
    op.add_column('users', sa.Column('gmail_token_expiry', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('gmail_history_id', sa.String(100), nullable=True))
    op.add_column('users', sa.Column('timezone', sa.String(50), server_default='UTC', nullable=False))
    op.add_column('users', sa.Column('last_email_sync_at', sa.DateTime(timezone=True), nullable=True))

    # Create documents table
    op.create_table(
        'documents',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('source', sa.String(50), nullable=False),
        sa.Column('title', sa.String(500), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('file_type', sa.String(50), nullable=True),
        sa.Column('status', sa.String(50), server_default='pending', nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.Index('idx_documents_user_id', 'user_id'),
    )

    # Create gmail_messages table
    op.create_table(
        'gmail_messages',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('gmail_message_id', sa.String(255), nullable=False),
        sa.Column('subject', sa.String(500), nullable=True),
        sa.Column('sender', sa.String(255), nullable=True),
        sa.Column('received_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('synced_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', sa.String(50), server_default='pending', nullable=False),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'gmail_message_id', name='uq_user_gmail_message'),
        sa.Index('idx_gmail_messages_user_id', 'user_id'),
        sa.Index('idx_user_synced', 'user_id', 'synced_at'),
    )


def downgrade() -> None:
    # Drop gmail_messages and documents tables
    op.drop_table('gmail_messages')
    op.drop_table('documents')

    # Remove Gmail and timezone fields from users table
    op.drop_column('users', 'last_email_sync_at')
    op.drop_column('users', 'timezone')
    op.drop_column('users', 'gmail_history_id')
    op.drop_column('users', 'gmail_token_expiry')
    op.drop_column('users', 'gmail_refresh_token')
    op.drop_column('users', 'gmail_access_token')
