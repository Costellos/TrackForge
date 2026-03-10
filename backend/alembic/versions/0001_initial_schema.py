"""Initial schema

Revision ID: 0001
Revises:
Create Date: 2026-03-08

"""
from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.execute("""
        CREATE TYPE artist_role AS ENUM
        ('primary','featured','producer','remixer','composer','conductor','other')
    """)
    op.execute("""
        CREATE TYPE trait_category AS ENUM
        ('performance','content','mastering','arrangement','edit','source','derivation','packaging')
    """)
    op.execute("""
        CREATE TYPE collection_type AS ENUM
        ('album','ep','single','compilation','soundtrack','live_set','dj_mix','mixtape','playlist','bootleg_release')
    """)
    op.execute("""
        CREATE TYPE id_provider AS ENUM
        ('musicbrainz','discogs','spotify','acoustid','isrc','upc','jellyfin','internal')
    """)
    op.execute("""
        CREATE TYPE asset_match_state AS ENUM
        ('unmatched','candidate','matched','rejected','needs_review')
    """)
    op.execute("""
        CREATE TYPE import_stage AS ENUM
        ('staged','extracting','fingerprinting','matching','scoring','awaiting_review','approved','rejected','imported')
    """)
    op.execute("""
        CREATE TYPE request_target_type AS ENUM ('song','version','collection','artist')
    """)
    op.execute("""
        CREATE TYPE request_status AS ENUM
        ('pending_approval','approved','searching','downloading','processing','available','failed','cancelled')
    """)
    op.execute("""
        CREATE TYPE adapter_type AS ENUM ('slskd','qbittorrent','nzbget','sabnzbd')
    """)
    op.execute("""
        CREATE TYPE job_status AS ENUM
        ('queued','submitted','downloading','completed','failed','cancelled')
    """)
    op.execute("CREATE TYPE user_role AS ENUM ('admin','moderator','user')")

    op.execute("""
        CREATE TABLE artists (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name            TEXT NOT NULL,
            sort_name       TEXT,
            disambiguation  TEXT,
            is_various      BOOLEAN NOT NULL DEFAULT FALSE,
            metadata        JSONB NOT NULL DEFAULT '{}',
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            deleted_at      TIMESTAMPTZ
        )
    """)
    op.execute("CREATE INDEX idx_artists_name_trgm ON artists USING GIN (name gin_trgm_ops)")

    op.execute("""
        CREATE TABLE songs (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            title           TEXT NOT NULL,
            canonical_year  SMALLINT,
            notes           TEXT,
            metadata        JSONB NOT NULL DEFAULT '{}',
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            deleted_at      TIMESTAMPTZ
        )
    """)
    op.execute("CREATE INDEX idx_songs_title_trgm ON songs USING GIN (title gin_trgm_ops)")

    op.execute("""
        CREATE TABLE artist_credits (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            song_id     UUID NOT NULL REFERENCES songs(id) ON DELETE CASCADE,
            artist_id   UUID NOT NULL REFERENCES artists(id),
            role        artist_role NOT NULL DEFAULT 'primary',
            credit_name TEXT,
            position    SMALLINT NOT NULL DEFAULT 0,
            UNIQUE (song_id, artist_id, role)
        )
    """)

    op.execute("""
        CREATE TABLE versions (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            song_id         UUID NOT NULL REFERENCES songs(id),
            title_override  TEXT,
            duration_ms     INTEGER,
            recording_date  DATE,
            notes           TEXT,
            metadata        JSONB NOT NULL DEFAULT '{}',
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            deleted_at      TIMESTAMPTZ
        )
    """)

    op.execute("""
        CREATE TABLE version_traits (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            version_id  UUID NOT NULL REFERENCES versions(id) ON DELETE CASCADE,
            category    trait_category NOT NULL,
            name        TEXT NOT NULL,
            source      TEXT,
            confidence  REAL NOT NULL DEFAULT 1.0,
            UNIQUE (version_id, category, name)
        )
    """)

    op.execute("""
        CREATE TABLE collections (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            title               TEXT NOT NULL,
            collection_type     collection_type NOT NULL DEFAULT 'album',
            primary_artist_id   UUID REFERENCES artists(id),
            release_date        DATE,
            label               TEXT,
            country             CHAR(2),
            notes               TEXT,
            metadata            JSONB NOT NULL DEFAULT '{}',
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            deleted_at          TIMESTAMPTZ
        )
    """)
    op.execute("CREATE INDEX idx_collections_title_trgm ON collections USING GIN (title gin_trgm_ops)")

    op.execute("""
        CREATE TABLE version_collection_entries (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            version_id      UUID NOT NULL REFERENCES versions(id),
            collection_id   UUID NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
            disc_number     SMALLINT NOT NULL DEFAULT 1,
            track_number    SMALLINT,
            title_override  TEXT,
            UNIQUE (collection_id, disc_number, track_number)
        )
    """)

    op.execute("""
        CREATE TABLE external_identifiers (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            entity_type TEXT NOT NULL,
            entity_id   UUID NOT NULL,
            provider    id_provider NOT NULL,
            external_id TEXT NOT NULL,
            is_primary  BOOLEAN NOT NULL DEFAULT FALSE,
            confidence  REAL NOT NULL DEFAULT 1.0,
            metadata    JSONB NOT NULL DEFAULT '{}',
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (provider, external_id, entity_type)
        )
    """)
    op.execute("CREATE INDEX idx_ext_ids_entity ON external_identifiers (entity_type, entity_id)")
    op.execute("CREATE INDEX idx_ext_ids_lookup ON external_identifiers (provider, external_id)")

    op.execute("""
        CREATE TABLE users (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            username            TEXT NOT NULL UNIQUE,
            email               TEXT UNIQUE,
            password_hash       TEXT,
            role                user_role NOT NULL DEFAULT 'user',
            jellyfin_user_id    TEXT UNIQUE,
            preferences         JSONB NOT NULL DEFAULT '{}',
            is_active           BOOLEAN NOT NULL DEFAULT TRUE,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_login_at       TIMESTAMPTZ
        )
    """)

    op.execute("""
        CREATE TABLE requests (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id         UUID NOT NULL REFERENCES users(id),
            approved_by     UUID REFERENCES users(id),
            target_type     request_target_type NOT NULL,
            target_id       UUID NOT NULL,
            status          request_status NOT NULL DEFAULT 'pending_approval',
            search_params   JSONB NOT NULL DEFAULT '{}',
            user_notes      TEXT,
            admin_notes     TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            resolved_at     TIMESTAMPTZ
        )
    """)
    op.execute("CREATE INDEX idx_requests_user ON requests (user_id)")
    op.execute("CREATE INDEX idx_requests_status ON requests (status)")
    op.execute("CREATE INDEX idx_requests_target ON requests (target_type, target_id)")

    op.execute("""
        CREATE TABLE acquisition_jobs (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            request_id          UUID NOT NULL REFERENCES requests(id),
            adapter             adapter_type NOT NULL,
            external_id         TEXT,
            status              job_status NOT NULL DEFAULT 'queued',
            source_query        TEXT,
            source_url          TEXT,
            bytes_total         BIGINT,
            bytes_downloaded    BIGINT,
            error_message       TEXT,
            started_at          TIMESTAMPTZ,
            completed_at        TIMESTAMPTZ,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE media_assets (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            version_id      UUID REFERENCES versions(id),
            file_path       TEXT NOT NULL UNIQUE,
            file_size       BIGINT,
            format          TEXT,
            bitrate         INTEGER,
            sample_rate     INTEGER,
            bit_depth       SMALLINT,
            channels        SMALLINT,
            duration_ms     INTEGER,
            checksum        TEXT,
            fingerprint     TEXT,
            match_state     asset_match_state NOT NULL DEFAULT 'unmatched',
            match_confidence REAL,
            raw_tags        JSONB NOT NULL DEFAULT '{}',
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE import_candidates (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            media_asset_id      UUID NOT NULL REFERENCES media_assets(id),
            acquisition_job_id  UUID REFERENCES acquisition_jobs(id),
            stage               import_stage NOT NULL DEFAULT 'staged',
            candidates          JSONB NOT NULL DEFAULT '[]',
            selected_version_id UUID REFERENCES versions(id),
            reviewer_notes      TEXT,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE library_items (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            version_id          UUID REFERENCES versions(id),
            jellyfin_item_id    TEXT UNIQUE,
            file_path           TEXT,
            last_seen_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            metadata            JSONB NOT NULL DEFAULT '{}'
        )
    """)

    op.execute("""
        CREATE TABLE audit_log (
            id          BIGSERIAL PRIMARY KEY,
            user_id     UUID REFERENCES users(id),
            action      TEXT NOT NULL,
            entity_type TEXT,
            entity_id   UUID,
            detail      JSONB NOT NULL DEFAULT '{}',
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)


def downgrade() -> None:
    for table in [
        "audit_log", "library_items", "import_candidates", "media_assets",
        "acquisition_jobs", "requests", "users", "external_identifiers",
        "version_collection_entries", "collections", "version_traits",
        "versions", "artist_credits", "songs", "artists",
    ]:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")

    for enum in [
        "user_role", "job_status", "adapter_type", "request_status",
        "request_target_type", "import_stage", "asset_match_state",
        "id_provider", "collection_type", "trait_category", "artist_role",
    ]:
        op.execute(f"DROP TYPE IF EXISTS {enum}")
