"""create token blacklist table

Revision ID: create_token_blacklist
Revises: add_username_unique
Create Date: 2026-05-20 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision: str = 'create_token_blacklist'
down_revision: Union[str, Sequence[str], None] = 'add_username_unique'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'token_blacklist',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('token_jti', sa.String(255), unique=True, nullable=False, index=True),
        sa.Column('token_type', sa.String(50), nullable=False),
        sa.Column('reason', sa.String(100), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('user_id', UUID(as_uuid=True), nullable=False, index=True),
    )


def downgrade() -> None:
    op.drop_table('token_blacklist')