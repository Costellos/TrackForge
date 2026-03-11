"""
Library endpoints — Jellyfin library data.
"""

import re

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from trackforge.adapters.library.jellyfin import JellyfinClient
from trackforge.adapters.metadata import musicbrainz as mb
from trackforge.api.deps import get_current_user, require_admin
from trackforge.config import get_settings
from trackforge.database import get_db
from trackforge.db.models import LibraryItem, User
from trackforge.domain.services.jellyfin_sync_service import (
    auto_resolve_requests,
    check_library_status,
    get_recently_added,
    sync_jellyfin_library,
)
from trackforge.domain.services.settings_service import get_all_settings as get_db_settings

log = structlog.get_logger()

router = APIRouter(prefix="/library", tags=["library"])


class RecentlyAddedItem(BaseModel):
    jellyfin_item_id: str | None
    name: str
    artist_name: str
    mbid: str | None
    release_mbid: str | None = None
    artist_mbid: str | None
    year: int | None
    date_created: str | None


class LibraryStatusBody(BaseModel):
    mbids: list[str]


class LibraryStatusResponse(BaseModel):
    statuses: dict[str, str | None]
    jellyfin_url: str | None = None


class RecentlyAddedResponse(BaseModel):
    items: list[RecentlyAddedItem]
    jellyfin_url: str | None = None


@router.get("/recently-added", response_model=RecentlyAddedResponse)
async def recently_added(
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Return recently added albums from the Jellyfin library."""
    db_settings = await get_db_settings(db)
    items = await get_recently_added(db, limit=limit)
    return RecentlyAddedResponse(
        items=items,
        jellyfin_url=db_settings.get("jellyfin_external_url") or None,
    )


@router.post("/status", response_model=LibraryStatusResponse)
async def library_status(
    body: LibraryStatusBody,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """
    Given a list of MusicBrainz release-group MBIDs, return which ones
    are already in the Jellyfin library.
    """
    db_settings = await get_db_settings(db)
    statuses = await check_library_status(db, body.mbids)
    return LibraryStatusResponse(
        statuses=statuses,
        jellyfin_url=db_settings.get("jellyfin_external_url") or None,
    )


class LibrarySearchItem(BaseModel):
    jellyfin_item_id: str
    name: str
    artist_name: str
    year: int | None = None


class LibrarySearchResponse(BaseModel):
    items: list[LibrarySearchItem]


@router.get("/search", response_model=LibrarySearchResponse)
async def search_library(
    q: str = Query("", min_length=1, max_length=200),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Search the synced Jellyfin library by album/artist name."""
    result = await db.execute(select(LibraryItem).where(LibraryItem.jellyfin_item_id.isnot(None)))
    items = result.scalars().all()

    query_lower = q.lower()
    matches = []
    for item in items:
        meta = item.metadata_ or {}
        name = meta.get("name", "")
        artist = meta.get("artist_name", "")
        if query_lower in name.lower() or query_lower in artist.lower():
            matches.append(LibrarySearchItem(
                jellyfin_item_id=item.jellyfin_item_id,
                name=name,
                artist_name=artist,
                year=meta.get("year"),
            ))
        if len(matches) >= 20:
            break

    return LibrarySearchResponse(items=matches)


class JellyfinItemResponse(BaseModel):
    id: str
    jellyfin_item_id: str
    name: str
    artist_name: str
    year: int | None = None
    mbid: str | None = None
    release_mbid: str | None = None
    artist_mbid: str | None = None
    date_created: str | None = None


class JellyfinItemsResponse(BaseModel):
    items: list[JellyfinItemResponse]
    jellyfin_url: str | None = None
    total: int


@router.get("/items", response_model=JellyfinItemsResponse)
async def list_jellyfin_items(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Return all albums synced from Jellyfin."""
    db_settings = await get_db_settings(db)
    result = await db.execute(
        select(LibraryItem).where(LibraryItem.jellyfin_item_id.isnot(None))
    )
    items = result.scalars().all()

    entries = []
    for item in items:
        meta = item.metadata_ or {}
        entries.append(JellyfinItemResponse(
            id=item.id,
            jellyfin_item_id=item.jellyfin_item_id,
            name=meta.get("name", ""),
            artist_name=meta.get("artist_name", ""),
            year=meta.get("year"),
            mbid=meta.get("mbid"),
            release_mbid=meta.get("release_mbid"),
            artist_mbid=meta.get("artist_mbid"),
            date_created=meta.get("date_created"),
        ))

    # Sort by name for consistent display
    entries.sort(key=lambda e: e.name.lower())

    return JellyfinItemsResponse(
        items=entries,
        jellyfin_url=db_settings.get("jellyfin_external_url") or None,
        total=len(entries),
    )


class LinkMusicBrainzBody(BaseModel):
    release_group_mbid: str


@router.post("/items/{item_id}/link-musicbrainz", response_model=JellyfinItemResponse)
async def link_musicbrainz(
    item_id: str,
    body: LinkMusicBrainzBody,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Link a Jellyfin library item to a MusicBrainz release group (admin only)."""
    result = await db.execute(
        select(LibraryItem).where(LibraryItem.id == item_id)
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Library item not found")

    meta = dict(item.metadata_ or {})
    meta["mbid"] = body.release_group_mbid
    item.metadata_ = meta
    await db.commit()

    return JellyfinItemResponse(
        id=item.id,
        jellyfin_item_id=item.jellyfin_item_id,
        name=meta.get("name", ""),
        artist_name=meta.get("artist_name", ""),
        year=meta.get("year"),
        mbid=meta.get("mbid"),
        release_mbid=meta.get("release_mbid"),
        artist_mbid=meta.get("artist_mbid"),
        date_created=meta.get("date_created"),
    )


class ScanResponse(BaseModel):
    synced: int
    resolved: int


@router.post("/scan", response_model=ScanResponse)
async def trigger_scan(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Manually trigger a Jellyfin library sync (admin only)."""
    synced = await sync_jellyfin_library(db)
    resolved = await auto_resolve_requests(db)
    return ScanResponse(synced=synced, resolved=resolved)


@router.get("/image/{jellyfin_item_id}")
async def jellyfin_image(
    jellyfin_item_id: str,
):
    """Proxy album art from Jellyfin for items without MusicBrainz cover art."""
    settings = get_settings()
    if not settings.jellyfin_url or not settings.jellyfin_api_key:
        return Response(status_code=404)
    client = JellyfinClient(settings.jellyfin_url, settings.jellyfin_api_key)
    result = await client.get_image_bytes(jellyfin_item_id, max_width=300)
    if result is None:
        return Response(status_code=404)
    image_bytes, content_type = result
    return Response(
        content=image_bytes,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )


class ResolveResponse(BaseModel):
    release_group_mbid: str | None = None


@router.get("/resolve/{jellyfin_item_id}", response_model=ResolveResponse)
async def resolve_jellyfin_item(
    jellyfin_item_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """
    Resolve a Jellyfin item to a MusicBrainz release-group MBID.
    If the item already has MBIDs, returns them directly.
    Otherwise, searches MusicBrainz by album name + artist.
    """
    result = await db.execute(
        select(LibraryItem).where(LibraryItem.jellyfin_item_id == jellyfin_item_id)
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")

    meta = item.metadata_ or {}
    name = meta.get("name", "")
    artist = meta.get("artist_name", "")
    base_name = _strip_reissue_suffix(name).lower() if name else ""

    # Try release-group MBID first, but validate it matches the album name
    stored_mbid = meta.get("mbid") or None
    if stored_mbid:
        rg = await mb.get_release_group(stored_mbid)
        if rg:
            rg_title = (rg.get("title") or "").lower()
            # Accept if title matches the album name or the base name
            if rg_title and (rg_title in name.lower() or name.lower() in rg_title or
                             rg_title == base_name or base_name in rg_title):
                return ResolveResponse(release_group_mbid=stored_mbid)
            log.warning("jellyfin_resolve.mbid_mismatch",
                        jf_name=name, mb_title=rg.get("title"), mbid=stored_mbid)

    # Try release MBID → resolve to release-group
    release_mbid = meta.get("release_mbid") or None
    if release_mbid:
        rg_mbid = await mb.get_release_group_mbid_for_release(release_mbid)
        if rg_mbid:
            return ResolveResponse(release_group_mbid=rg_mbid)

    # Search MusicBrainz by name + artist
    if not name:
        return ResolveResponse()

    resolved = await _resolve_by_search(name, artist, meta.get("artist_mbid"))
    if resolved:
        return ResolveResponse(release_group_mbid=resolved)
    return ResolveResponse()


def _escape_lucene(text: str) -> str:
    """Escape Lucene special characters for MusicBrainz search."""
    special = r'+-&|!(){}[]^"~*?:\/'
    out = []
    for ch in text:
        if ch in special:
            out.append(f"\\{ch}")
        else:
            out.append(ch)
    return "".join(out)


_REISSUE_RE = re.compile(
    r"\s*[\(\[]\s*"
    r"(?:\d+\w*\s+anniversary|deluxe|remaster(?:ed)?|expanded|special|bonus|"
    r"super\s+deluxe|collector'?s?|limited|redux|revisited)"
    r"[^\)\]]*[\)\]]",
    re.IGNORECASE,
)


def _strip_reissue_suffix(name: str) -> str:
    """Strip common reissue/deluxe suffixes like '(25th Anniversary)'."""
    return _REISSUE_RE.sub("", name).strip()


async def _resolve_by_search(
    name: str, artist: str, artist_mbid: str | None
) -> str | None:
    """Search MusicBrainz for a release group matching name + artist."""
    escaped = _escape_lucene(name)
    base_name = _strip_reissue_suffix(name)

    # Try searches in order: exact name, then base name (without reissue suffix)
    queries = [escaped]
    if base_name and base_name.lower() != name.lower():
        queries.append(_escape_lucene(base_name))

    for query in queries:
        if artist:
            query = f'"{query}" AND artist:"{_escape_lucene(artist)}"'
        results = await mb.search_release_groups(query, limit=5)
        if not results:
            continue

        name_lower = name.lower()
        base_lower = base_name.lower() if base_name else name_lower

        # Prefer exact title match
        for rg in results:
            title = rg.get("title", "").lower()
            if title == name_lower or title == base_lower:
                return rg["mbid"]

        # Accept close match: base name contained in result title
        for rg in results:
            title = rg.get("title", "").lower()
            if base_lower in title or title in base_lower:
                return rg["mbid"]

    # Last resort: return top result from first successful search
    escaped = _escape_lucene(name)
    query = f'"{escaped}" AND artist:"{_escape_lucene(artist)}"' if artist else f'"{escaped}"'
    results = await mb.search_release_groups(query, limit=1)
    if results:
        return results[0].get("mbid")

    return None
