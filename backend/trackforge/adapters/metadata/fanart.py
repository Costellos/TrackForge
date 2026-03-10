"""
Fanart.tv adapter — artist images.

Fetches artist thumbnails and backgrounds by MusicBrainz ID.
Cached in Redis for 7 days. Requires a free API key from fanart.tv.
"""

import httpx
import structlog

from trackforge.cache import cache_get, cache_set
from trackforge.config import get_settings

log = structlog.get_logger()
settings = get_settings()

FANART_BASE = "https://webservice.fanart.tv/v3/music"
CACHE_TTL = 60 * 60 * 24 * 7  # 7 days


async def get_artist_images(mbid: str) -> dict | None:
    """
    Fetch artist images from Fanart.tv.
    Returns a dict with 'thumb' and 'background' URLs, or None if not found.
    """
    if not settings.fanart_api_key:
        return None

    cache_key = f"fanart:artist:{mbid}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    log.info("fanart.get_artist", mbid=mbid)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{FANART_BASE}/{mbid}",
                params={"api_key": settings.fanart_api_key},
            )
            if resp.status_code == 404:
                # Cache the miss so we don't keep hitting the API
                result: dict = {"thumb": None, "background": None}
                await cache_set(cache_key, result, ttl=CACHE_TTL)
                return result
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPStatusError, httpx.RequestError):
        log.warning("fanart.get_artist.failed", mbid=mbid)
        return None

    # Pick best thumbnail
    thumbs = data.get("artistthumb", [])
    thumb_url = thumbs[0]["url"] if thumbs else None

    # Pick best background
    backgrounds = data.get("artistbackground", [])
    bg_url = backgrounds[0]["url"] if backgrounds else None

    result = {"thumb": thumb_url, "background": bg_url}
    await cache_set(cache_key, result, ttl=CACHE_TTL)
    return result
