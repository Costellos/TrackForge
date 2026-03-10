"""
Jellyfin library adapter.
Queries the Jellyfin API for music library contents and triggers scans.
"""

from typing import Any

import httpx
import structlog

log = structlog.get_logger()


class JellyfinClient:
    def __init__(self, base_url: str, api_key: str):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    def _headers(self) -> dict:
        return {"X-Emby-Token": self._api_key}

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=10.0) as c:
                resp = await c.get(
                    f"{self._base_url}/System/Info",
                    headers=self._headers(),
                )
                resp.raise_for_status()
                log.info("jellyfin.connected", server=resp.json().get("ServerName"))
                return True
        except Exception:
            return False

    async def trigger_scan(self) -> None:
        """Trigger a full library refresh scan."""
        async with httpx.AsyncClient(timeout=10.0) as c:
            resp = await c.post(
                f"{self._base_url}/Library/Refresh",
                headers=self._headers(),
            )
            resp.raise_for_status()
        log.info("jellyfin.scan_triggered")

    async def get_all_albums(self) -> list[dict[str, Any]]:
        """
        Fetch all music albums from Jellyfin.
        Returns a list of album items with their provider IDs.
        """
        items: list[dict[str, Any]] = []
        start = 0
        limit = 200

        async with httpx.AsyncClient(timeout=30.0) as c:
            while True:
                resp = await c.get(
                    f"{self._base_url}/Items",
                    headers=self._headers(),
                    params={
                        "IncludeItemTypes": "MusicAlbum",
                        "Recursive": "true",
                        "Fields": "ProviderIds,DateCreated,Path",
                        "StartIndex": start,
                        "Limit": limit,
                        "SortBy": "DateCreated",
                        "SortOrder": "Descending",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                batch = data.get("Items", [])
                items.extend(batch)

                total = data.get("TotalRecordCount", 0)
                start += limit
                if start >= total or not batch:
                    break

        log.info("jellyfin.albums_fetched", count=len(items))
        return items

    async def get_all_artists(self) -> list[dict[str, Any]]:
        """
        Fetch all album artists from Jellyfin.
        """
        items: list[dict[str, Any]] = []
        start = 0
        limit = 200

        async with httpx.AsyncClient(timeout=30.0) as c:
            while True:
                resp = await c.get(
                    f"{self._base_url}/Artists/AlbumArtists",
                    headers=self._headers(),
                    params={
                        "Fields": "ProviderIds",
                        "StartIndex": start,
                        "Limit": limit,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                batch = data.get("Items", [])
                items.extend(batch)

                total = data.get("TotalRecordCount", 0)
                start += limit
                if start >= total or not batch:
                    break

        log.info("jellyfin.artists_fetched", count=len(items))
        return items

    def get_image_url(self, item_id: str, max_width: int = 300) -> str:
        """Return the primary image URL for a Jellyfin item."""
        return f"{self._base_url}/Items/{item_id}/Images/Primary?maxWidth={max_width}"

    async def get_image_bytes(self, item_id: str, max_width: int = 300) -> tuple[bytes, str] | None:
        """Fetch the primary image for a Jellyfin item. Returns (bytes, content_type) or None."""
        url = self.get_image_url(item_id, max_width)
        try:
            async with httpx.AsyncClient(timeout=10.0) as c:
                resp = await c.get(url, headers=self._headers())
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                ct = resp.headers.get("content-type", "image/jpeg")
                return resp.content, ct
        except Exception:
            return None

    async def get_recently_added_albums(self, limit: int = 20) -> list[dict[str, Any]]:
        """
        Fetch recently added music albums from Jellyfin.
        """
        async with httpx.AsyncClient(timeout=15.0) as c:
            resp = await c.get(
                f"{self._base_url}/Items",
                headers=self._headers(),
                params={
                    "IncludeItemTypes": "MusicAlbum",
                    "Recursive": "true",
                    "Fields": "ProviderIds,DateCreated,Path",
                    "Limit": limit,
                    "SortBy": "DateCreated",
                    "SortOrder": "Descending",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("Items", [])
