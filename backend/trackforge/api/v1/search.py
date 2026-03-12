"""
Search endpoint — stateless proxy to external metadata providers.
Nothing is written to the database here.
"""

from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from trackforge.adapters.metadata import musicbrainz as mb
from trackforge.adapters.metadata.fanart import get_artist_images
from trackforge.adapters.metadata.preview import get_preview

router = APIRouter(prefix="/search", tags=["search"])


# ─────────────────────────────────────────────
# RESPONSE MODELS
# ─────────────────────────────────────────────

class ArtistResult(BaseModel):
    mbid: str | None
    name: str | None
    sort_name: str | None
    disambiguation: str | None
    type: str | None
    country: str | None
    begin: str | None
    end: str | None
    score: int | None


class ReleaseGroupResult(BaseModel):
    mbid: str | None
    title: str | None
    type: str | None
    secondary_types: list[str]
    first_release_date: str | None
    artists: list[dict]
    score: int | None


class RecordingResult(BaseModel):
    mbid: str | None
    title: str | None
    length_ms: int | None
    disambiguation: str | None
    artists: list[dict]
    releases: list[dict]
    score: int | None
    isrcs: list[str]


class SearchResponse(BaseModel):
    query: str
    type: str
    results: list[ArtistResult] | list[ReleaseGroupResult] | list[RecordingResult]


# ─────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────

@router.get("", response_model=SearchResponse)
async def search(
    q: str = Query(..., min_length=1, description="Search query"),
    type: Literal["artist", "album", "song"] = Query("artist", description="Type of search"),
    limit: int = Query(20, ge=1, le=50),
):
    """
    Search for artists, albums, or songs via MusicBrainz.
    Results are cached — nothing is written to the database.
    """
    if not q.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    if type == "artist":
        results = await mb.search_artists(q.strip(), limit=limit)
        return SearchResponse(query=q, type=type, results=results)

    if type == "album":
        results = await mb.search_release_groups(q.strip(), limit=limit)
        return SearchResponse(query=q, type=type, results=results)

    if type == "song":
        results = await mb.search_recordings(q.strip(), limit=limit)
        return SearchResponse(query=q, type=type, results=results)

    raise HTTPException(status_code=400, detail=f"Unknown search type: {type}")


@router.get("/artist/{mbid}")
async def get_artist(mbid: str):
    """Fetch a single artist with their release groups."""
    result = await mb.get_artist(mbid)
    if result is None:
        raise HTTPException(status_code=404, detail="Artist not found")

    # Attach Fanart.tv images if available
    images = await get_artist_images(mbid)
    result["image_thumb"] = images.get("thumb") if images else None
    result["image_background"] = images.get("background") if images else None

    return result


@router.get("/artist/{mbid}/images")
async def get_artist_image_urls(mbid: str):
    """Fetch artist images from Fanart.tv. Returns thumb + background URLs."""
    images = await get_artist_images(mbid)
    return {
        "mbid": mbid,
        "thumb": images.get("thumb") if images else None,
        "background": images.get("background") if images else None,
    }


@router.get("/album/{mbid}")
async def get_release_group(mbid: str):
    """Fetch a release group with its releases."""
    result = await mb.get_release_group(mbid)
    if result is None:
        raise HTTPException(status_code=404, detail="Release group not found")
    return result


VINYL_FORMATS = {"12\" Vinyl", "7\" Vinyl", "10\" Vinyl", "Vinyl", "Cassette"}


def _release_sort_key(r: dict) -> tuple:
    formats = set(r.get("formats", []))
    is_vinyl = bool(formats & VINYL_FORMATS) if formats else False
    track_count = r.get("track_count", 0)
    date = r.get("date", "9999")
    # Sort: non-vinyl first, then most tracks, then oldest date
    return (is_vinyl, -track_count, date)


def _release_label(r: dict) -> str:
    """Build a human-readable label for a release."""
    parts = []
    formats = r.get("formats", [])
    if formats:
        parts.append(" + ".join(dict.fromkeys(formats)))  # deduplicate preserving order
    if r.get("country"):
        parts.append(r["country"])
    if r.get("date"):
        parts.append(r["date"])
    tc = r.get("track_count", 0)
    if tc:
        parts.append(f"{tc} tracks")
    return " · ".join(parts) if parts else (r.get("title") or r.get("mbid", "Unknown"))


@router.get("/album/{mbid}/tracks")
async def get_album_tracks(mbid: str, release_mbid: str | None = None):
    """
    Get the tracklist for a release group.
    Picks the best release (CD/Digital, most tracks) by default.
    Pass ?release_mbid=... to select a specific release.
    Also accepts a release MBID as the path param — will resolve to its parent release-group.
    """
    rg = await mb.get_release_group(mbid)

    # If not found as a release-group, try as a release MBID
    rg_mbid = mbid
    if rg is None:
        rg_mbid_resolved = await mb.get_release_group_mbid_for_release(mbid)
        if rg_mbid_resolved:
            rg_mbid = rg_mbid_resolved
            rg = await mb.get_release_group(rg_mbid)

    if rg is None:
        raise HTTPException(status_code=404, detail="Album not found")

    releases = rg.get("releases", [])

    # Build release options for the frontend
    sorted_releases = sorted(releases, key=_release_sort_key) if releases else []
    release_options = [
        {"mbid": r["mbid"], "label": _release_label(r)}
        for r in sorted_releases
    ]

    if not releases:
        return {
            "release_group_mbid": rg_mbid,
            "album_title": rg.get("title"),
            "album_type": rg.get("type"),
            "album_secondary_types": rg.get("secondary_types", []),
            "first_release_date": rg.get("first_release_date"),
            "artists": rg.get("artists", []),
            "tracks": [],
            "releases": release_options,
        }

    # Use specific release if requested, otherwise pick best
    chosen = None
    if release_mbid:
        chosen = next((r for r in releases if r["mbid"] == release_mbid), None)
    if not chosen:
        chosen = sorted_releases[0]

    release = await mb.get_release(chosen["mbid"])
    if release is None:
        raise HTTPException(status_code=404, detail="Release not found")

    release["release_group_mbid"] = rg_mbid
    release["release_mbid"] = chosen["mbid"]
    release["album_title"] = rg.get("title")
    release["album_type"] = rg.get("type")
    release["album_secondary_types"] = rg.get("secondary_types", [])
    release["first_release_date"] = rg.get("first_release_date")
    release["artists"] = rg.get("artists", [])
    release["releases"] = release_options
    return release


class PreviewResponse(BaseModel):
    source: str  # "spotify", "itunes", "youtube", "none"
    url: str | None


@router.get("/preview/{recording_mbid}", response_model=PreviewResponse)
async def get_track_preview(recording_mbid: str):
    """
    Find a ~30s audio preview for a recording.
    Tries Spotify → iTunes → YouTube in order.
    """
    from trackforge.adapters.metadata.musicbrainz import cache_get, cache_set

    # Check Redis cache first
    cache_key = f"preview:{recording_mbid}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return PreviewResponse(**cached)

    # Look up the recording from MusicBrainz to get ISRCs + metadata
    recording = await mb.get_recording(recording_mbid)
    if recording is None:
        raise HTTPException(status_code=404, detail="Recording not found")

    title = recording.get("title") or ""
    artists = recording.get("artists", [])
    artist = artists[0]["name"] if artists else ""
    isrcs = recording.get("isrcs", [])

    result = await get_preview(recording_mbid, title, artist, isrcs)

    # Cache for 24 hours
    await cache_set(cache_key, result, ttl=60 * 60 * 24)

    return PreviewResponse(**result)
