"""alter users table for new schema

Revision ID: alter_users_001
Revises: a5363bfb6c27
Create Date: 2026-05-20 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision: str = 'alter_users_001'
down_revision: Union[str, Sequence[str], None] = 'a5363bfb6c27'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Columns already exist from 9512adebaf3b - only drop legacy columns
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_cols = {c['name'] for c in inspector.get_columns('users')}
    
    if 'provider' in existing_cols:
        op.drop_column('users', 'provider')
    if 'is_deleted' in existing_cols:
        op.drop_column('users', 'is_deleted')


def downgrade() -> None:
    op.add_column('users', sa.Column('provider', sa.String(50), nullable=True))
    op.add_column('users', sa.Column('is_deleted', sa.Boolean(), default=False))