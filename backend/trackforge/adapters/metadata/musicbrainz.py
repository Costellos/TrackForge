"""
MusicBrainz metadata adapter.

Queries the MusicBrainz API directly via httpx.
All results are cached in Redis. Nothing is written to the database here —
that only happens when a user requests or monitors something.

Rate limit: MusicBrainz allows 1 request/second for identified clients.
We stay well within this with async httpx and Redis caching.
"""

import asyncio
from typing import Any

import httpx
import structlog

from trackforge.cache import cache_get, cache_set
from trackforge.config import get_settings

log = structlog.get_logger()
settings = get_settings()

MB_BASE = "https://musicbrainz.org/ws/2"
HEADERS = {
    "User-Agent": (
        f"{settings.musicbrainz_app_name}/{settings.musicbrainz_app_version}"
        f" ( {settings.musicbrainz_contact} )"
    ),
    "Accept": "application/json",
}

# Rate limiting — MB allows 1 req/sec, we use a simple async lock + sleep
_mb_lock = asyncio.Lock()
_last_request_time: float = 0.0


async def _get(path: str, params: dict[str, Any]) -> dict:
    """Make a rate-limited GET request to MusicBrainz."""
    global _last_request_time
    import time

    async with _mb_lock:
        now = time.monotonic()
        wait = 1.1 - (now - _last_request_time)
        if wait > 0:
            await asyncio.sleep(wait)

        async with httpx.AsyncClient(headers=HEADERS, timeout=10.0) as client:
            resp = await client.get(f"{MB_BASE}{path}", params=params)
            resp.raise_for_status()
            _last_request_time = time.monotonic()
            return resp.json()


# ─────────────────────────────────────────────
# ARTIST SEARCH
# ─────────────────────────────────────────────

async def search_artists(query: str, limit: int = 20) -> list[dict]:
    """
    Search for artists by name.
    Returns a list of normalized artist dicts.
    Cached for 7 days.
    """
    cache_key = f"mb:artist_search:{query.lower()}:{limit}"
    cached = await cache_get(cache_key)
    if cached is not None:
        log.debug("mb.artist_search.cache_hit", query=query)
        return cached

    log.info("mb.artist_search", query=query)
    data = await _get("/artist", {
        "query": query,
        "limit": limit,
        "fmt": "json",
    })

    results = [_normalize_artist(a) for a in data.get("artists", [])]
    await cache_set(cache_key, results, ttl=settings.cache_ttl_artist)
    return results


async def get_artist(mbid: str) -> dict | None:
    """
    Fetch a single artist by MBID with release groups included.
    Cached for 7 days.
    """
    cache_key = f"mb:artist:{mbid}"
    cached = await cache_get(cache_key)
    if cached is not None:
        log.debug("mb.get_artist.cache_hit", mbid=mbid)
        return cached

    log.info("mb.get_artist", mbid=mbid)
    try:
        data = await _get(f"/artist/{mbid}", {
            "inc": "release-groups+aliases",
            "fmt": "json",
        })
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return None
        raise

    result = _normalize_artist(data, include_release_groups=True)
    await cache_set(cache_key, result, ttl=settings.cache_ttl_artist)
    return result


# ─────────────────────────────────────────────
# RELEASE GROUP SEARCH (albums, EPs, etc.)
# ─────────────────────────────────────────────

async def search_release_groups(
    query: str,
    artist_mbid: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """
    Search for release groups (albums, EPs, singles, etc.).
    Optionally scoped to a specific artist MBID.
    Cached for 24 hours.
    """
    artist_part = artist_mbid or "any"
    cache_key = f"mb:rg_search:{query.lower()}:{artist_part}:{limit}"
    cached = await cache_get(cache_key)
    if cached is not None:
        log.debug("mb.rg_search.cache_hit", query=query)
        return cached

    mb_query = query
    if artist_mbid:
        mb_query = f"{query} AND arid:{artist_mbid}"

    log.info("mb.rg_search", query=mb_query)
    data = await _get("/release-group", {
        "query": mb_query,
        "limit": limit,
        "fmt": "json",
    })

    results = [_normalize_release_group(rg) for rg in data.get("release-groups", [])]
    await cache_set(cache_key, results, ttl=settings.cache_ttl_search)
    return results


async def get_release_group(mbid: str) -> dict | None:
    """
    Fetch a release group with its releases and tracks.
    Cached for 7 days.
    """
    cache_key = f"mb:rg:{mbid}"
    cached = await cache_get(cache_key)
    if cached is not None:
        log.debug("mb.get_rg.cache_hit", mbid=mbid)
        return cached

    log.info("mb.get_rg", mbid=mbid)
    try:
        data = await _get(f"/release-group/{mbid}", {
            "inc": "artists+releases+media",
            "fmt": "json",
        })
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return None
        raise

    result = _normalize_release_group(data, include_releases=True)
    await cache_set(cache_key, result, ttl=settings.cache_ttl_artist)
    return result


async def get_release(mbid: str) -> dict | None:
    """
    Fetch a specific release (pressing) with its full tracklist.
    Cached for 7 days.
    """
    cache_key = f"mb:release:{mbid}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    log.info("mb.get_release", mbid=mbid)
    try:
        data = await _get(f"/release/{mbid}", {
            "inc": "recordings+artist-credits",
            "fmt": "json",
        })
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return None
        raise

    tracks = []
    for medium in data.get("media", []):
        disc = medium.get("position", 1)
        for track in medium.get("tracks", []):
            recording = track.get("recording", {})
            tracks.append({
                "disc": disc,
                "position": track.get("position"),
                "number": track.get("number"),
                "title": track.get("title") or recording.get("title"),
                "length_ms": track.get("length") or recording.get("length"),
                "recording_mbid": recording.get("id"),
            })

    result = {
        "mbid": data.get("id"),
        "title": data.get("title"),
        "date": data.get("date"),
        "country": data.get("country"),
        "tracks": tracks,
    }
    await cache_set(cache_key, result, ttl=settings.cache_ttl_artist)
    return result


async def get_release_group_mbid_for_release(release_mbid: str) -> str | None:
    """
    Look up a release and return its parent release-group MBID.
    Cached for 7 days.
    """
    cache_key = f"mb:release_rg:{release_mbid}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached if cached != "__none__" else None

    log.info("mb.get_release_rg", release_mbid=release_mbid)
    try:
        data = await _get(f"/release/{release_mbid}", {
            "inc": "release-groups",
            "fmt": "json",
        })
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            await cache_set(cache_key, "__none__", ttl=settings.cache_ttl_artist)
            return None
        raise

    rg = data.get("release-group", {})
    rg_mbid = rg.get("id")
    await cache_set(cache_key, rg_mbid or "__none__", ttl=settings.cache_ttl_artist)
    return rg_mbid


# ─────────────────────────────────────────────
# RECORDING SEARCH (individual songs)
# ─────────────────────────────────────────────

async def get_recording(mbid: str) -> dict | None:
    """
    Fetch a single recording with ISRCs and artist credits.
    Cached for 7 days.
    """
    cache_key = f"mb:recording:{mbid}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    log.info("mb.get_recording", mbid=mbid)
    try:
        data = await _get(f"/recording/{mbid}", {
            "inc": "artists+isrcs+releases",
            "fmt": "json",
        })
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return None
        raise

    result = _normalize_recording(data)
    await cache_set(cache_key, result, ttl=settings.cache_ttl_artist)
    return result


async def search_recordings(
    query: str,
    artist_mbid: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """
    Search for recordings (individual songs/tracks).
    Cached for 24 hours.
    """
    artist_part = artist_mbid or "any"
    cache_key = f"mb:rec_search:{query.lower()}:{artist_part}:{limit}"
    cached = await cache_get(cache_key)
    if cached is not None:
        log.debug("mb.rec_search.cache_hit", query=query)
        return cached

    mb_query = query
    if artist_mbid:
        mb_query = f"{query} AND arid:{artist_mbid}"

    log.info("mb.rec_search", query=mb_query)
    data = await _get("/recording", {
        "query": mb_query,
        "limit": limit,
        "fmt": "json",
    })

    results = [_normalize_recording(r) for r in data.get("recordings", [])]
    await cache_set(cache_key, results, ttl=settings.cache_ttl_search)
    return results


# ─────────────────────────────────────────────
# NORMALIZATION HELPERS
# ─────────────────────────────────────────────

def _normalize_artist(data: dict, include_release_groups: bool = False) -> dict:
    result: dict[str, Any] = {
        "mbid": data.get("id"),
        "name": data.get("name"),
        "sort_name": data.get("sort-name"),
        "disambiguation": data.get("disambiguation"),
        "type": data.get("type"),
        "country": data.get("country"),
        "score": data.get("score"),
    }

    life_span = data.get("life-span", {})
    result["begin"] = life_span.get("begin")
    result["end"] = life_span.get("end")
    result["ended"] = life_span.get("ended", False)

    if include_release_groups:
        result["release_groups"] = [
            _normalize_release_group(rg)
            for rg in data.get("release-groups", [])
        ]

    return result


def _normalize_release_group(data: dict, include_releases: bool = False) -> dict:
    # Collect all artist credits
    artists = []
    for credit in data.get("artist-credit", []):
        if isinstance(credit, dict) and "artist" in credit:
            artists.append({
                "mbid": credit["artist"].get("id"),
                "name": credit.get("name") or credit["artist"].get("name"),
            })

    result: dict[str, Any] = {
        "mbid": data.get("id"),
        "title": data.get("title"),
        "type": data.get("primary-type"),
        "secondary_types": data.get("secondary-types", []),
        "first_release_date": data.get("first-release-date"),
        "artists": artists,
        "score": data.get("score"),
    }

    if include_releases:
        result["releases"] = []
        for r in data.get("releases", []):
            media = r.get("media", [])
            formats = [m.get("format", "") for m in media if m.get("format")]
            track_count = sum(m.get("track-count", 0) for m in media)
            result["releases"].append({
                "mbid": r.get("id"),
                "title": r.get("title"),
                "date": r.get("date"),
                "country": r.get("country"),
                "status": r.get("status"),
                "formats": formats,
                "track_count": track_count,
            })

    return result


def _normalize_recording(data: dict) -> dict:
    artists = []
    for credit in data.get("artist-credit", []):
        if isinstance(credit, dict) and "artist" in credit:
            artists.append({
                "mbid": credit["artist"].get("id"),
                "name": credit.get("name") or credit["artist"].get("name"),
            })

    releases = []
    for r in data.get("releases", []):
        releases.append({
            "mbid": r.get("id"),
            "title": r.get("title"),
            "date": r.get("date"),
        })

    return {
        "mbid": data.get("id"),
        "title": data.get("title"),
        "length_ms": data.get("length"),
        "disambiguation": data.get("disambiguation"),
        "artists": artists,
        "releases": releases,
        "score": data.get("score"),
        "isrcs": data.get("isrcs", []),
    }
