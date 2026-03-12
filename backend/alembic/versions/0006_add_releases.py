"""Add releases table (specific editions of a release group/collection)

Revision ID: 0006
Revises: 0005
Create Date: 2026-03-12

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create releases table
    op.create_table(
        "releases",
        sa.Column("id", UUID(as_uuid=False), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("collection_id", UUID(as_uuid=False), sa.ForeignKey("collections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.Text, nullable=True),
        sa.Column("release_date", sa.Date, nullable=True),
        sa.Column("country", sa.String(2), nullable=True),
        sa.Column("label", sa.Text, nullable=True),
        sa.Column("edition_name", sa.Text, nullable=True),
        sa.Column("musicbrainz_release_id", sa.Text, nullable=True),
        sa.Column("metadata", JSONB, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_releases_collection", "releases", ["collection_id"])

    # Add release_id to version_collection_entries (nullable for now)
    op.add_column(
        "version_collection_entries",
        sa.Column("release_id", UUID(as_uuid=False), sa.ForeignKey("releases.id", ondelete="CASCADE"), nullable=True),
    )

    # Backfill: create a default release for each collection that has entries,
    # then point existing entries at the new releases.
    # This is done in raw SQL for efficiency.
    op.execute("""
        INSERT INTO releases (id, collection_id, title, release_date, country, label)
        SELECT gen_random_uuid(), c.id, NULL, c.release_date, c.country, c.label
        FROM collections c
        WHERE EXISTS (
            SELECT 1 FROM version_collection_entries vce WHERE vce.collection_id = c.id
        )
    """)

    op.execute("""
        UPDATE version_collection_entries vce
        SET release_id = r.id
        FROM releases r
        WHERE r.collection_id = vce.collection_id
    """)


def downgrade() -> None:
    op.drop_column("version_collection_entries", "release_id")
    op.drop_index("idx_releases_collection")
    op.drop_table("releases")
