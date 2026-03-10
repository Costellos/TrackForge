"""
ListenBrainz adapter — trending/popular data.

Queries the ListenBrainz API for sitewide statistics.
All results are cached in Redis. No API key required.
"""

import httpx
import structlog

from trackforge.cache import cache_get, cache_set
from trackforge.config import get_settings

log = structlog.get_logger()
settings = get_settings()

LB_BASE = "https://api.listenbrainz.org"
HEADERS = {
    "User-Agent": f"{settings.musicbrainz_app_name}/{settings.musicbrainz_app_version}",
    "Accept": "application/json",
}

# Cache trending data for 6 hours
TRENDING_TTL = 60 * 60 * 6


async def _get(path: str, params: dict | None = None) -> dict:
    async with httpx.AsyncClient(headers=HEADERS, timeout=15.0) as client:
        resp = await client.get(f"{LB_BASE}{path}", params=params or {})
        resp.raise_for_status()
        return resp.json()


async def get_trending_release_groups(count: int = 20, range_: str = "week") -> list[dict]:
    """
    Fetch sitewide top release groups (trending albums).
    Returns normalized list with cover art info.
    """
    cache_key = f"lb:trending_rg:{range_}:{count}"
    cached = await cache_get(cache_key)
    if cached is not None:
        log.debug("lb.trending_rg.cache_hit", range=range_)
        return cached

    log.info("lb.trending_rg", range=range_, count=count)
    try:
        data = await _get("/1/stats/sitewide/release-groups", {
            "count": count,
            "range": range_,
        })
    except httpx.HTTPStatusError:
        log.warning("lb.trending_rg.failed", range=range_)
        return []

    items = []
    for rg in data.get("payload", {}).get("release_groups", []):
        items.append({
            "release_group_mbid": rg.get("release_group_mbid"),
            "title": rg.get("release_group_name"),
            "artist_name": rg.get("artist_name"),
            "artist_mbids": rg.get("artist_mbids", []),
            "listen_count": rg.get("listen_count"),
            "caa_id": rg.get("caa_id"),
            "caa_release_mbid": rg.get("caa_release_mbid"),
        })

    await cache_set(cache_key, items, ttl=TRENDING_TTL)
    return items


async def get_trending_artists(count: int = 20, range_: str = "week") -> list[dict]:
    """
    Fetch sitewide top artists.
    """
    cache_key = f"lb:trending_artists:{range_}:{count}"
    cached = await cache_get(cache_key)
    if cached is not None:
        log.debug("lb.trending_artists.cache_hit", range=range_)
        return cached

    log.info("lb.trending_artists", range=range_, count=count)
    try:
        data = await _get("/1/stats/sitewide/artists", {
            "count": count,
            "range": range_,
        })
    except httpx.HTTPStatusError:
        log.warning("lb.trending_artists.failed", range=range_)
        return []

    items = []
    for a in data.get("payload", {}).get("artists", []):
        items.append({
            "artist_mbid": a.get("artist_mbid"),
            "artist_name": a.get("artist_name"),
            "listen_count": a.get("listen_count"),
        })

    await cache_set(cache_key, items, ttl=TRENDING_TTL)
    return items
