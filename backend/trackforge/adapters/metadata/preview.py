"""
Song preview adapter.

Tries multiple sources in priority order to find a ~30-second preview clip:
  1. Spotify  — requires client_id + client_secret (client credentials flow)
  2. iTunes   — free, no auth needed
  3. YouTube  — free, returns search URL for iframe embed

Results are cached in Redis for 24 hours.
"""

import base64
import urllib.parse

import httpx
import structlog

from trackforge.config import get_settings

log = structlog.get_logger()
settings = get_settings()

# Module-level token cache for Spotify (single-process; good enough for API + worker)
_spotify_token: str | None = None
_spotify_token_expires: float = 0


async def get_preview(
    recording_mbid: str,
    title: str,
    artist: str,
    isrcs: list[str],
) -> dict:
    """
    Try each source in order. Returns:
      { source: "spotify"|"itunes"|"youtube"|"none", url: str|None }
    """
    # 1. Spotify
    url = await _try_spotify(title, artist, isrcs)
    if url:
        return {"source": "spotify", "url": url}

    # 2. iTunes
    url = await _try_itunes(title, artist, isrcs)
    if url:
        return {"source": "itunes", "url": url}

    # 3. YouTube (search URL for embed)
    url = _youtube_search_url(title, artist)
    if url:
        return {"source": "youtube", "url": url}

    return {"source": "none", "url": None}


# ─────────────────────────────────────────────
# SPOTIFY
# ─────────────────────────────────────────────

async def _get_spotify_token() -> str | None:
    """Get a Spotify access token via client credentials flow."""
    import time

    global _spotify_token, _spotify_token_expires

    if _spotify_token and time.time() < _spotify_token_expires - 60:
        return _spotify_token

    if not settings.spotify_client_id or not settings.spotify_client_secret:
        return None

    creds = base64.b64encode(
        f"{settings.spotify_client_id}:{settings.spotify_client_secret}".encode()
    ).decode()

    try:
        async with httpx.AsyncClient(timeout=10) as c:
            resp = await c.post(
                "https://accounts.spotify.com/api/token",
                data={"grant_type": "client_credentials"},
                headers={"Authorization": f"Basic {creds}"},
            )
            resp.raise_for_status()
            data = resp.json()
            _spotify_token = data["access_token"]
            _spotify_token_expires = time.time() + data.get("expires_in", 3600)
            return _spotify_token
    except Exception as e:
        log.warning("preview.spotify_token_failed", error=str(e))
        return None


async def _try_spotify(title: str, artist: str, isrcs: list[str]) -> str | None:
    token = await _get_spotify_token()
    if not token:
        return None

    headers = {"Authorization": f"Bearer {token}"}

    try:
        async with httpx.AsyncClient(timeout=10, headers=headers) as c:
            # Try ISRC first (most accurate match)
            for isrc in isrcs[:3]:
                resp = await c.get(
                    "https://api.spotify.com/v1/search",
                    params={"q": f"isrc:{isrc}", "type": "track", "limit": 1},
                )
                if resp.status_code == 200:
                    items = resp.json().get("tracks", {}).get("items", [])
                    if items and items[0].get("preview_url"):
                        log.debug("preview.spotify_isrc_hit", isrc=isrc)
                        return items[0]["preview_url"]

            # Fall back to text search
            q = f"track:{title} artist:{artist}"
            resp = await c.get(
                "https://api.spotify.com/v1/search",
                params={"q": q, "type": "track", "limit": 3},
            )
            if resp.status_code == 200:
                for item in resp.json().get("tracks", {}).get("items", []):
                    if item.get("preview_url"):
                        log.debug("preview.spotify_search_hit", title=title)
                        return item["preview_url"]

    except Exception as e:
        log.warning("preview.spotify_failed", error=str(e))

    return None


# ─────────────────────────────────────────────
# ITUNES
# ─────────────────────────────────────────────

async def _try_itunes(title: str, artist: str, isrcs: list[str]) -> str | None:
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            # Try ISRC lookup via iTunes
            for isrc in isrcs[:2]:
                resp = await c.get(
                    "https://itunes.apple.com/lookup",
                    params={"isrc": isrc, "entity": "song"},
                )
                if resp.status_code == 200:
                    results = resp.json().get("results", [])
                    for r in results:
                        url = r.get("previewUrl")
                        if url:
                            log.debug("preview.itunes_isrc_hit", isrc=isrc)
                            return url

            # Fall back to text search
            term = f"{artist} {title}"
            resp = await c.get(
                "https://itunes.apple.com/search",
                params={"term": term, "media": "music", "entity": "song", "limit": 5},
            )
            if resp.status_code == 200:
                for r in resp.json().get("results", []):
                    url = r.get("previewUrl")
                    if url:
                        log.debug("preview.itunes_search_hit", title=title)
                        return url

    except Exception as e:
        log.warning("preview.itunes_failed", error=str(e))

    return None


# ─────────────────────────────────────────────
# YOUTUBE
# ─────────────────────────────────────────────

def _youtube_search_url(title: str, artist: str) -> str:
    """Return a YouTube search URL that the frontend can embed or link to."""
    q = f"{artist} - {title}"
    return f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(q)}"
