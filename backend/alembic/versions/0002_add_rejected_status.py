"""Add rejected status to request_status enum

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-09

"""
from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE request_status ADD VALUE IF NOT EXISTS 'rejected'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values; downgrade is a no-op
    pass
