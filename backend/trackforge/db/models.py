"""
SQLAlchemy ORM models. These map directly to the database schema.
Domain logic lives in trackforge/domain/, not here.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from trackforge.database import Base

# ─────────────────────────────────────────────
# ENUMS
# ─────────────────────────────────────────────

ArtistRoleEnum = Enum(
    "primary", "featured", "producer", "remixer", "composer", "conductor", "other",
    name="artist_role",
)

TraitCategoryEnum = Enum(
    "performance", "content", "mastering", "arrangement",
    "edit", "source", "derivation", "packaging",
    name="trait_category",
)

CollectionTypeEnum = Enum(
    "album", "ep", "single", "compilation", "soundtrack",
    "live_set", "dj_mix", "mixtape", "playlist", "bootleg_release",
    name="collection_type",
)

IdProviderEnum = Enum(
    "musicbrainz", "discogs", "spotify", "acoustid", "isrc", "upc", "jellyfin", "internal",
    name="id_provider",
)

AssetMatchStateEnum = Enum(
    "unmatched", "candidate", "matched", "rejected", "needs_review",
    name="asset_match_state",
)

ImportStageEnum = Enum(
    "staged", "extracting", "fingerprinting", "matching",
    "scoring", "awaiting_review", "approved", "rejected", "imported",
    name="import_stage",
)

RequestTargetTypeEnum = Enum(
    "song", "version", "collection", "artist",
    name="request_target_type",
)

RequestStatusEnum = Enum(
    "pending_approval", "approved", "searching", "downloading",
    "processing", "pending_review", "available", "failed", "cancelled", "rejected",
    name="request_status",
)

AdapterTypeEnum = Enum(
    "slskd", "qbittorrent", "nzbget", "sabnzbd",
    name="adapter_type",
)

JobStatusEnum = Enum(
    "queued", "submitted", "downloading", "completed", "failed", "cancelled",
    name="job_status",
)

UserRoleEnum = Enum("admin", "moderator", "user", name="user_role")


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.utcnow()


# ─────────────────────────────────────────────
# ARTISTS
# ─────────────────────────────────────────────

class Artist(Base):
    __tablename__ = "artists"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    sort_name: Mapped[str | None] = mapped_column(Text)
    disambiguation: Mapped[str | None] = mapped_column(Text)
    is_various: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    credits: Mapped[list["ArtistCredit"]] = relationship(back_populates="artist")
    external_ids: Mapped[list["ExternalIdentifier"]] = relationship(
        primaryjoin="and_(ExternalIdentifier.entity_type=='artist', foreign(ExternalIdentifier.entity_id)==Artist.id)",
        viewonly=True,
    )


# ─────────────────────────────────────────────
# SONGS
# ─────────────────────────────────────────────

class Song(Base):
    __tablename__ = "songs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_year: Mapped[int | None] = mapped_column(SmallInteger)
    notes: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    credits: Mapped[list["ArtistCredit"]] = relationship(back_populates="song")
    versions: Mapped[list["Version"]] = relationship(back_populates="song")


class ArtistCredit(Base):
    __tablename__ = "artist_credits"
    __table_args__ = (UniqueConstraint("song_id", "artist_id", "role"),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    song_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("songs.id", ondelete="CASCADE"), nullable=False)
    artist_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("artists.id"), nullable=False)
    role: Mapped[str] = mapped_column(ArtistRoleEnum, nullable=False, default="primary")
    credit_name: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)

    song: Mapped["Song"] = relationship(back_populates="credits")
    artist: Mapped["Artist"] = relationship(back_populates="credits")


# ─────────────────────────────────────────────
# VERSIONS
# ─────────────────────────────────────────────

class Version(Base):
    __tablename__ = "versions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    song_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("songs.id"), nullable=False)
    title_override: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    recording_date: Mapped[datetime | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    song: Mapped["Song"] = relationship(back_populates="versions")
    traits: Mapped[list["VersionTrait"]] = relationship(back_populates="version", cascade="all, delete-orphan")
    collection_entries: Mapped[list["VersionCollectionEntry"]] = relationship(back_populates="version")
    media_assets: Mapped[list["MediaAsset"]] = relationship(back_populates="version")


class VersionTrait(Base):
    __tablename__ = "version_traits"
    __table_args__ = (UniqueConstraint("version_id", "category", "name"),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    version_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("versions.id", ondelete="CASCADE"), nullable=False)
    category: Mapped[str] = mapped_column(TraitCategoryEnum, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)

    version: Mapped["Version"] = relationship(back_populates="traits")


# ─────────────────────────────────────────────
# COLLECTIONS
# ─────────────────────────────────────────────

class Collection(Base):
    __tablename__ = "collections"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    collection_type: Mapped[str] = mapped_column(CollectionTypeEnum, nullable=False, default="album")
    primary_artist_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("artists.id"))
    release_date: Mapped[datetime | None] = mapped_column(Date)
    label: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str | None] = mapped_column(String(2))
    notes: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    primary_artist: Mapped["Artist | None"] = relationship()
    releases: Mapped[list["Release"]] = relationship(back_populates="collection", cascade="all, delete-orphan")
    version_entries: Mapped[list["VersionCollectionEntry"]] = relationship(back_populates="collection", cascade="all, delete-orphan")


class Release(Base):
    __tablename__ = "releases"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    collection_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("collections.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str | None] = mapped_column(Text)  # NULL = same as collection title
    release_date: Mapped[datetime | None] = mapped_column(Date)
    country: Mapped[str | None] = mapped_column(String(2))
    label: Mapped[str | None] = mapped_column(Text)
    edition_name: Mapped[str | None] = mapped_column(Text)  # "Deluxe Edition", "Japan Import"
    musicbrainz_release_id: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    collection: Mapped["Collection"] = relationship(back_populates="releases")
    track_entries: Mapped[list["VersionCollectionEntry"]] = relationship(back_populates="release")


class VersionCollectionEntry(Base):
    __tablename__ = "version_collection_entries"
    __table_args__ = (UniqueConstraint("collection_id", "disc_number", "track_number"),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    version_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("versions.id"), nullable=False)
    collection_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("collections.id", ondelete="CASCADE"), nullable=False)
    release_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("releases.id", ondelete="CASCADE"))
    disc_number: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    track_number: Mapped[int | None] = mapped_column(SmallInteger)
    title_override: Mapped[str | None] = mapped_column(Text)

    version: Mapped["Version"] = relationship(back_populates="collection_entries")
    collection: Mapped["Collection"] = relationship(back_populates="version_entries")
    release: Mapped["Release | None"] = relationship(back_populates="track_entries")


# ─────────────────────────────────────────────
# EXTERNAL IDENTIFIERS
# ─────────────────────────────────────────────

class ExternalIdentifier(Base):
    __tablename__ = "external_identifiers"
    __table_args__ = (UniqueConstraint("provider", "external_id", "entity_type"),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    provider: Mapped[str] = mapped_column(IdProviderEnum, nullable=False)
    external_id: Mapped[str] = mapped_column(Text, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ─────────────────────────────────────────────
# MEDIA ASSETS
# ─────────────────────────────────────────────

class MediaAsset(Base):
    __tablename__ = "media_assets"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    version_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("versions.id"))
    file_path: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    file_size: Mapped[int | None] = mapped_column(BigInteger)
    format: Mapped[str | None] = mapped_column(Text)
    bitrate: Mapped[int | None] = mapped_column(Integer)
    sample_rate: Mapped[int | None] = mapped_column(Integer)
    bit_depth: Mapped[int | None] = mapped_column(SmallInteger)
    channels: Mapped[int | None] = mapped_column(SmallInteger)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    checksum: Mapped[str | None] = mapped_column(Text)
    fingerprint: Mapped[str | None] = mapped_column(Text)
    match_state: Mapped[str] = mapped_column(AssetMatchStateEnum, nullable=False, default="unmatched")
    match_confidence: Mapped[float | None] = mapped_column(Float)
    raw_tags: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    version: Mapped["Version | None"] = relationship(back_populates="media_assets")


# ─────────────────────────────────────────────
# IMPORT CANDIDATES
# ─────────────────────────────────────────────

class ImportCandidate(Base):
    __tablename__ = "import_candidates"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    media_asset_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("media_assets.id"), nullable=False)
    acquisition_job_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("acquisition_jobs.id"))
    stage: Mapped[str] = mapped_column(ImportStageEnum, nullable=False, default="staged")
    candidates: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    selected_version_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("versions.id"))
    reviewer_notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    media_asset: Mapped["MediaAsset"] = relationship()
    selected_version: Mapped["Version | None"] = relationship()


# ─────────────────────────────────────────────
# USERS
# ─────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    email: Mapped[str | None] = mapped_column(Text, unique=True)
    password_hash: Mapped[str | None] = mapped_column(Text)
    role: Mapped[str] = mapped_column(UserRoleEnum, nullable=False, default="user")
    jellyfin_user_id: Mapped[str | None] = mapped_column(Text, unique=True)
    preferences: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    requests: Mapped[list["Request"]] = relationship(back_populates="user", foreign_keys="Request.user_id")


# ─────────────────────────────────────────────
# REQUESTS
# ─────────────────────────────────────────────

class Request(Base):
    __tablename__ = "requests"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    approved_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"))
    target_type: Mapped[str] = mapped_column(RequestTargetTypeEnum, nullable=False)
    target_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    status: Mapped[str] = mapped_column(RequestStatusEnum, nullable=False, default="pending_approval")
    search_params: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    user_notes: Mapped[str | None] = mapped_column(Text)
    admin_notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship(back_populates="requests", foreign_keys=[user_id])
    approver: Mapped["User | None"] = relationship(foreign_keys=[approved_by])
    acquisition_jobs: Mapped[list["AcquisitionJob"]] = relationship(back_populates="request")


# ─────────────────────────────────────────────
# ACQUISITION JOBS
# ─────────────────────────────────────────────

class AcquisitionJob(Base):
    __tablename__ = "acquisition_jobs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    request_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("requests.id", ondelete="CASCADE"), nullable=False)
    adapter: Mapped[str] = mapped_column(AdapterTypeEnum, nullable=False)
    external_id: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(JobStatusEnum, nullable=False, default="queued")
    source_query: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    bytes_total: Mapped[int | None] = mapped_column(BigInteger)
    bytes_downloaded: Mapped[int | None] = mapped_column(BigInteger)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    request: Mapped["Request"] = relationship(back_populates="acquisition_jobs")


# ─────────────────────────────────────────────
# LIBRARY ITEMS
# ─────────────────────────────────────────────

class LibraryItem(Base):
    __tablename__ = "library_items"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    version_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("versions.id"))
    jellyfin_item_id: Mapped[str | None] = mapped_column(Text, unique=True)
    file_path: Mapped[str | None] = mapped_column(Text)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)

    version: Mapped["Version | None"] = relationship()


# ─────────────────────────────────────────────
# APP SETTINGS
# ─────────────────────────────────────────────

class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ─────────────────────────────────────────────
# AUDIT LOG
# ─────────────────────────────────────────────

class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str | None] = mapped_column(Text)
    entity_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False))
    detail: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
