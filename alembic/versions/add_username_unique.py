"""add unique index to username

Revision ID: add_username_unique
Revises: alter_users_001
Create Date: 2026-05-20 18:30:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'add_username_unique'
down_revision: Union[str, Sequence[str], None] = 'alter_users_001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint('uq_users_username', 'users', ['username'])


def downgrade() -> None:
    op.drop_constraint('uq_users_username', 'users', type_='unique')