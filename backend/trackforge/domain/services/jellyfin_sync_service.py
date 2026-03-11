"""
Jellyfin library sync service.

Syncs album and artist data from Jellyfin into the library_items table,
using MusicBrainz IDs (ProviderIds) to link Jellyfin items to local entities.

This runs periodically via a worker cron job.
"""

import json
from datetime import datetime, timezone

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy.orm import selectinload

from trackforge.adapters.library.jellyfin import JellyfinClient
from trackforge.cache import cache_delete, cache_get, cache_set
from trackforge.config import get_settings
from trackforge.db.models import Collection, ExternalIdentifier, LibraryItem, Request

log = structlog.get_logger()

CACHE_KEY = "jellyfin:library"
CACHE_TTL = 60 * 15  # 15 minutes
RECENTLY_ADDED_KEY = "jellyfin:recently_added"
RECENTLY_ADDED_TTL = 60 * 10  # 10 minutes


def _get_client() -> JellyfinClient | None:
    settings = get_settings()
    if not settings.jellyfin_url or not settings.jellyfin_api_key:
        return None
    return JellyfinClient(settings.jellyfin_url, settings.jellyfin_api_key)


def _extract_mbid(item: dict) -> str | None:
    """Extract MusicBrainz release group ID from Jellyfin ProviderIds."""
    provider_ids = item.get("ProviderIds", {})
    return provider_ids.get("MusicBrainzReleaseGroup") or None


def _extract_release_mbid(item: dict) -> str | None:
    """Extract MusicBrainz release (album) ID from Jellyfin ProviderIds."""
    provider_ids = item.get("ProviderIds", {})
    return provider_ids.get("MusicBrainzAlbum") or None


def _extract_artist_mbid(item: dict) -> str | None:
    """Extract MusicBrainz artist ID from Jellyfin ProviderIds."""
    provider_ids = item.get("ProviderIds", {})
    return provider_ids.get("MusicBrainzArtist") or None


async def sync_jellyfin_library(db: AsyncSession) -> int:
    """
    Full sync: fetch all albums from Jellyfin and upsert into library_items.
    Returns the number of items synced.
    """
    client = _get_client()
    if client is None:
        return 0

    try:
        albums = await client.get_all_albums()
    except Exception as e:
        log.error("jellyfin_sync.fetch_failed", error=str(e))
        return 0

    # Build a map of jellyfin_item_id -> album data
    jellyfin_items: dict[str, dict] = {}
    for album in albums:
        jf_id = album.get("Id")
        if jf_id:
            jellyfin_items[jf_id] = album

    # Load existing library items
    result = await db.execute(select(LibraryItem))
    existing = {item.jellyfin_item_id: item for item in result.scalars().all() if item.jellyfin_item_id}

    now = datetime.now(timezone.utc)
    synced = 0

    # Upsert items from Jellyfin
    for jf_id, album in jellyfin_items.items():
        mbid = _extract_mbid(album)
        release_mbid = _extract_release_mbid(album)
        artist_name = album.get("AlbumArtist") or album.get("Artist") or ""
        metadata = {
            "name": album.get("Name", ""),
            "artist_name": artist_name,
            "mbid": mbid,
            "release_mbid": release_mbid,
            "artist_mbid": _extract_artist_mbid(album),
            "year": album.get("ProductionYear"),
            "date_created": album.get("DateCreated"),
        }

        if jf_id in existing:
            item = existing[jf_id]
            item.last_seen_at = now
            item.metadata_ = metadata
            item.file_path = album.get("Path")
        else:
            item = LibraryItem(
                jellyfin_item_id=jf_id,
                file_path=album.get("Path"),
                last_seen_at=now,
                metadata_=metadata,
            )
            db.add(item)

        synced += 1

    # Remove library items no longer in Jellyfin
    stale_ids = set(existing.keys()) - set(jellyfin_items.keys())
    if stale_ids:
        await db.execute(
            delete(LibraryItem).where(LibraryItem.jellyfin_item_id.in_(list(stale_ids)))
        )
        log.info("jellyfin_sync.removed_stale", count=len(stale_ids))

    await db.commit()

    # Invalidate cache
    await cache_delete(CACHE_KEY)
    await cache_delete(RECENTLY_ADDED_KEY)

    log.info("jellyfin_sync.complete", synced=synced, removed=len(stale_ids))
    return synced


async def get_library_mbids(db: AsyncSession) -> dict[str, str]:
    """
    Return a dict mapping MusicBrainz release-group MBIDs to Jellyfin item IDs
    for all albums currently in the Jellyfin library.
    Cached in Redis for 15 minutes.
    """
    cached = await cache_get(CACHE_KEY)
    if cached is not None:
        return cached

    result = await db.execute(select(LibraryItem).where(LibraryItem.jellyfin_item_id.isnot(None)))
    items = result.scalars().all()

    mbid_map: dict[str, str] = {}
    for item in items:
        meta = item.metadata_ or {}
        jf_id = item.jellyfin_item_id
        if not jf_id:
            continue
        # Index by release-group MBID
        mbid = meta.get("mbid")
        if mbid:
            mbid_map[mbid] = jf_id
        # Also index by release MBID so lookups work with either ID type
        release_mbid = meta.get("release_mbid")
        if release_mbid:
            mbid_map[release_mbid] = jf_id

    await cache_set(CACHE_KEY, mbid_map, ttl=CACHE_TTL)
    return mbid_map


async def get_recently_added(db: AsyncSession, limit: int = 20) -> list[dict]:
    """
    Return recently added albums from the Jellyfin library.
    Cached in Redis for 10 minutes.
    """
    cache_key = f"{RECENTLY_ADDED_KEY}:{limit}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    result = await db.execute(
        select(LibraryItem)
        .where(LibraryItem.jellyfin_item_id.isnot(None))
        .order_by(LibraryItem.last_seen_at.desc())
        .limit(limit)
    )
    items = result.scalars().all()

    entries = []
    for item in items:
        meta = item.metadata_ or {}
        entries.append({
            "jellyfin_item_id": item.jellyfin_item_id,
            "name": meta.get("name", ""),
            "artist_name": meta.get("artist_name", ""),
            "mbid": meta.get("mbid"),
            "release_mbid": meta.get("release_mbid"),
            "artist_mbid": meta.get("artist_mbid"),
            "year": meta.get("year"),
            "date_created": meta.get("date_created"),
        })

    await cache_set(cache_key, entries, ttl=RECENTLY_ADDED_TTL)
    return entries


async def check_library_status(db: AsyncSession, mbids: list[str]) -> dict[str, str | None]:
    """
    Given a list of MusicBrainz release-group MBIDs, return a mapping of
    MBID → jellyfin_item_id (or None if not in library).
    """
    if not mbids:
        return {}

    library_mbids = await get_library_mbids(db)
    return {mbid: library_mbids.get(mbid) for mbid in mbids}


ACTIVE_STATUSES = {"approved", "searching", "downloading", "processing"}


async def auto_resolve_requests(db: AsyncSession) -> int:
    """
    After a library sync, check active requests whose collections are now
    in the Jellyfin library and mark them as available.
    Returns the number of requests resolved.
    """
    from trackforge.domain.services.notification_service import notify_request_status

    # Get all active collection requests
    result = await db.execute(
        select(Request).where(
            Request.target_type == "collection",
            Request.status.in_(ACTIVE_STATUSES),
        )
    )
    active_requests = result.scalars().all()
    if not active_requests:
        return 0

    # Get library MBIDs (freshly cached after sync)
    library_mbids = await get_library_mbids(db)
    if not library_mbids:
        return 0

    # Build a map of collection_id -> request for active requests
    collection_ids = [r.target_id for r in active_requests]

    # Look up MBIDs for these collections via external_identifiers
    ext_result = await db.execute(
        select(ExternalIdentifier).where(
            ExternalIdentifier.entity_type == "collection",
            ExternalIdentifier.entity_id.in_(collection_ids),
            ExternalIdentifier.provider == "musicbrainz",
        )
    )
    ext_ids = ext_result.scalars().all()

    # Map collection_id -> mbid
    collection_mbid_map = {ext.entity_id: ext.external_id for ext in ext_ids}

    now = datetime.now(timezone.utc)
    resolved = 0

    for req in active_requests:
        mbid = collection_mbid_map.get(req.target_id)
        if not mbid:
            continue
        if mbid in library_mbids:
            req.status = "available"
            req.resolved_at = now
            req.updated_at = now
            resolved += 1
            log.info(
                "jellyfin_sync.auto_resolved",
                request_id=req.id,
                mbid=mbid,
            )

    if resolved:
        await db.commit()
        # Send notifications for resolved requests
        for req in active_requests:
            if req.status == "available":
                await notify_request_status(db, req)

    return resolved
