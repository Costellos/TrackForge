"""Add ON DELETE CASCADE to acquisition_jobs.request_id FK

Revision ID: 0005
Revises: 0004
Create Date: 2026-03-12

"""
from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("acquisition_jobs_request_id_fkey", "acquisition_jobs", type_="foreignkey")
    op.create_foreign_key(
        "acquisition_jobs_request_id_fkey",
        "acquisition_jobs",
        "requests",
        ["request_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("acquisition_jobs_request_id_fkey", "acquisition_jobs", type_="foreignkey")
    op.create_foreign_key(
        "acquisition_jobs_request_id_fkey",
        "acquisition_jobs",
        "requests",
        ["request_id"],
        ["id"],
    )
