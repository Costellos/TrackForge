"""Add app_settings table

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-09

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.Text, primary_key=True),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    # Seed defaults
    op.execute(
        "INSERT INTO app_settings (key, value) VALUES "
        "('registration_enabled', 'true'), "
        "('require_approval', 'true')"
    )


def downgrade() -> None:
    op.drop_table("app_settings")
