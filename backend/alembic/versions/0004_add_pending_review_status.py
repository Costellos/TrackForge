"""Add pending_review status to request_status enum

Revision ID: 0004
Revises: 0003
Create Date: 2026-03-11

"""
from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE request_status ADD VALUE IF NOT EXISTS 'pending_review'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values; downgrade is a no-op
    pass
