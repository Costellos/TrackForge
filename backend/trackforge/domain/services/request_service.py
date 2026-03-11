"""
Request service.

Handles materializing external search results into local DB entities,
then creating Request records against them.

This is the boundary where "browse data" becomes "owned data".
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from trackforge.db.models import (
    Artist,
    ArtistCredit,
    AuditLog,
    Collection,
    ExternalIdentifier,
    Request,
    Song,
    Version,
)


# ─────────────────────────────────────────────
# ENTITY MATERIALIZATION
# ─────────────────────────────────────────────

async def get_or_create_artist(db: AsyncSession, mbid: str, name: str, sort_name: str | None = None) -> Artist:
    """
    Look up an artist by MusicBrainz ID.
    Creates a local record if one doesn't exist yet.
    """
    result = await db.execute(
        select(ExternalIdentifier).where(
            ExternalIdentifier.provider == "musicbrainz",
            ExternalIdentifier.external_id == mbid,
            ExternalIdentifier.entity_type == "artist",
        )
    )
    ext_id = result.scalar_one_or_none()

    if ext_id:
        artist = await db.get(Artist, ext_id.entity_id)
        if artist:
            return artist

    artist = Artist(
        id=str(uuid.uuid4()),
        name=name,
        sort_name=sort_name or name,
    )
    db.add(artist)
    await db.flush()

    db.add(ExternalIdentifier(
        id=str(uuid.uuid4()),
        entity_type="artist",
        entity_id=artist.id,
        provider="musicbrainz",
        external_id=mbid,
        is_primary=True,
        confidence=1.0,
    ))

    return artist


async def get_or_create_collection(
    db: AsyncSession,
    mbid: str,
    title: str,
    collection_type: str,
    artist_mbid: str | None,
    artist_name: str | None,
    release_date: str | None,
) -> Collection:
    """
    Look up a collection (album/EP/etc.) by MusicBrainz release group ID.
    Creates a local record if one doesn't exist yet.
    """
    result = await db.execute(
        select(ExternalIdentifier).where(
            ExternalIdentifier.provider == "musicbrainz",
            ExternalIdentifier.external_id == mbid,
            ExternalIdentifier.entity_type == "collection",
        )
    )
    ext_id = result.scalar_one_or_none()

    if ext_id:
        collection = await db.get(Collection, ext_id.entity_id)
        if collection:
            # Backfill primary artist if it was missing when first created
            if not collection.primary_artist_id and artist_mbid and artist_name:
                artist = await get_or_create_artist(db, artist_mbid, artist_name)
                collection.primary_artist_id = artist.id
                await db.flush()
            return collection

    # Resolve or create the primary artist if provided
    primary_artist_id = None
    if artist_mbid and artist_name:
        artist = await get_or_create_artist(db, artist_mbid, artist_name)
        primary_artist_id = artist.id

    # Normalize collection type to our enum values
    type_map = {
        "Album": "album",
        "EP": "ep",
        "Single": "single",
        "Compilation": "compilation",
        "Soundtrack": "soundtrack",
        "Live": "live_set",
        "DJ-mix": "dj_mix",
        "Mixtape/Street": "mixtape",
        "Bootleg": "bootleg_release",
    }
    normalized_type = type_map.get(collection_type, "album")

    # Parse release date
    from datetime import date
    parsed_date = None
    if release_date:
        try:
            parts = release_date.split("-")
            if len(parts) == 3:
                parsed_date = date(int(parts[0]), int(parts[1]), int(parts[2]))
            elif len(parts) == 2:
                parsed_date = date(int(parts[0]), int(parts[1]), 1)
            elif len(parts) == 1 and parts[0]:
                parsed_date = date(int(parts[0]), 1, 1)
        except (ValueError, IndexError):
            pass

    collection = Collection(
        id=str(uuid.uuid4()),
        title=title,
        collection_type=normalized_type,
        primary_artist_id=primary_artist_id,
        release_date=parsed_date,
    )
    db.add(collection)
    await db.flush()

    db.add(ExternalIdentifier(
        id=str(uuid.uuid4()),
        entity_type="collection",
        entity_id=collection.id,
        provider="musicbrainz",
        external_id=mbid,
        is_primary=True,
        confidence=1.0,
    ))

    return collection


async def get_or_create_song(
    db: AsyncSession,
    recording_mbid: str,
    title: str,
    artist_mbid: str | None,
    artist_name: str | None,
    length_ms: int | None = None,
) -> Song:
    """
    Look up a song by MusicBrainz recording ID.
    Creates Song + Version + ArtistCredit if one doesn't exist yet.
    Returns the Song (the request targets the Song).
    """
    # Check if we already have this recording
    result = await db.execute(
        select(ExternalIdentifier).where(
            ExternalIdentifier.provider == "musicbrainz",
            ExternalIdentifier.external_id == recording_mbid,
            ExternalIdentifier.entity_type == "song",
        )
    )
    ext_id = result.scalar_one_or_none()

    if ext_id:
        song = await db.get(Song, ext_id.entity_id)
        if song:
            return song

    # Create the song
    song = Song(
        id=str(uuid.uuid4()),
        title=title,
    )
    db.add(song)
    await db.flush()

    # Create a version for this specific recording
    version = Version(
        id=str(uuid.uuid4()),
        song_id=song.id,
        duration_ms=length_ms,
    )
    db.add(version)
    await db.flush()

    # Link artist
    if artist_mbid and artist_name:
        artist = await get_or_create_artist(db, artist_mbid, artist_name)
        db.add(ArtistCredit(
            id=str(uuid.uuid4()),
            song_id=song.id,
            artist_id=artist.id,
            role="primary",
            position=0,
        ))

    # Store external identifier for the song (recording MBID)
    db.add(ExternalIdentifier(
        id=str(uuid.uuid4()),
        entity_type="song",
        entity_id=song.id,
        provider="musicbrainz",
        external_id=recording_mbid,
        is_primary=True,
        confidence=1.0,
    ))

    return song


# ─────────────────────────────────────────────
# REQUEST CREATION
# ─────────────────────────────────────────────

async def create_request(
    db: AsyncSession,
    user_id: str,
    target_type: str,
    target_id: str,
    user_notes: str | None = None,
    search_params: dict | None = None,
    auto_approve: bool = False,
) -> Request:
    """
    Create a request. If auto_approve is True (e.g. for admins),
    status is set to 'approved' immediately.
    """
    # Check for duplicate pending/approved request
    existing = await db.execute(
        select(Request).where(
            Request.user_id == user_id,
            Request.target_type == target_type,
            Request.target_id == target_id,
            Request.status.in_(["pending_approval", "approved", "searching", "downloading", "processing"]),
        )
    )
    if existing.scalar_one_or_none():
        raise ValueError("You already have an active request for this item")

    status = "approved" if auto_approve else "pending_approval"

    request = Request(
        id=str(uuid.uuid4()),
        user_id=user_id,
        approved_by=user_id if auto_approve else None,
        target_type=target_type,
        target_id=target_id,
        status=status,
        search_params=search_params or {},
        user_notes=user_notes,
    )
    db.add(request)

    db.add(AuditLog(
        user_id=user_id,
        action="request.created",
        entity_type=target_type,
        entity_id=target_id,
        detail={"status": status, "auto_approve": auto_approve},
    ))

    await db.flush()
    return request
