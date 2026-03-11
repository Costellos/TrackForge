"""
Prowlarr search adapter.

Uses the per-indexer Newznab-compatible API that Prowlarr exposes at:
  GET {prowlarr_url}/{indexer_id}/api?t=search&q={query}&apikey={key}

NZB files are fetched via:
  GET {prowlarr_url}/{indexer_id}/api?t=get&id={guid}&apikey={key}

This fetches through Prowlarr (which handles indexer auth) so we get the
actual NZB bytes without IP restrictions or expired redirect tokens.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import xml.etree.ElementTree as ET

import httpx
import structlog

log = structlog.get_logger()

_NEWZNAB_NS = "http://www.newznab.com/DTD/2010/feeds/attributes/"
_VIDEO_KEYWORDS = ("720p", "1080p", "2160p", "4k", "bluray", "blu-ray", "dvdrip", "hdtv", "x265", "hevc", "h264")
_AUDIO_CATS = {3000, 3010, 3020, 3030, 3040, 3050}


@dataclass
class ProwlarrResult:
    title: str
    download_url: str
    guid: str
    indexer_id: int
    size: int           # bytes
    indexer: str
    age_days: float
    grabs: int
    categories: list[int]

    @property
    def is_video(self) -> bool:
        t = self.title.lower()
        return any(kw in t for kw in _VIDEO_KEYWORDS)

    @property
    def format_score(self) -> int:
        title_lower = self.title.lower()
        cats = set(self.categories)
        if 3040 in cats or "flac" in title_lower or "lossless" in title_lower or "web-flac" in title_lower:
            return 3
        if 3010 in cats or "mp3" in title_lower:
            if "320" in self.title:
                return 2
            return 1
        if cats & _AUDIO_CATS:
            return 2
        return 1

    @property
    def score(self) -> float:
        age_penalty = min(self.age_days / 365, 1.0)
        grabs_bonus = min(self.grabs / 10, 1.0)
        return self.format_score * 10 + grabs_bonus * 2 - age_penalty


class ProwlarrClient:
    def __init__(self, base_url: str, api_key: str):
        self._base = base_url.rstrip("/")
        self._api_key = api_key
        self._headers = {"X-Api-Key": api_key}

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(headers=self._headers, timeout=60.0)

    async def health_check(self) -> bool:
        try:
            async with self._client() as c:
                r = await c.get(f"{self._base}/api/v1/indexer")
                return r.status_code == 200
        except Exception:
            return False

    async def _get_indexers(self) -> list[dict]:
        """Return enabled indexers with id and priority from Prowlarr."""
        async with self._client() as c:
            resp = await c.get(f"{self._base}/api/v1/indexer")
            resp.raise_for_status()
            return [
                {"id": i["id"], "priority": i.get("priority", 25), "name": i.get("name", "")}
                for i in resp.json() if i.get("enable")
            ]

    def _extract_guid_id(self, guid_url: str) -> str:
        """
        Extract the raw NZB ID from an indexer GUID URL.
        NZBGeek:   https://nzbgeek.info/geekseek.php?guid=abc123  → abc123
        NZBFinder: https://nzbfinder.ws/details/uuid-here          → uuid-here
        """
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(guid_url)
        qs = parse_qs(parsed.query)
        if "guid" in qs:
            return qs["guid"][0]
        # Last path segment (NZBFinder style)
        return parsed.path.rstrip("/").split("/")[-1]

    async def get_nzb(self, result: ProwlarrResult) -> bytes:
        """
        Fetch the NZB file bytes for a result.
        Tries t=get first (Prowlarr proxies auth), falls back to direct download URL.
        """
        nzb_id = self._extract_guid_id(result.guid)
        log.info("prowlarr.get_nzb", indexer_id=result.indexer_id, nzb_id=nzb_id)

        headers = {"User-Agent": "NZBGet/21.1", "Accept": "application/x-nzb, */*"}

        # Try t=get first
        try:
            url = f"{self._base}/{result.indexer_id}/api"
            params = {"t": "get", "id": nzb_id, "apikey": self._api_key}
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, headers=headers) as c:
                resp = await c.get(url, params=params)
                resp.raise_for_status()
                if resp.content:
                    log.info("prowlarr.get_nzb_via_tget", bytes=len(resp.content))
                    return resp.content
        except Exception as e:
            log.warning("prowlarr.tget_failed", nzb_id=nzb_id, error=str(e))

        # Fall back to direct download URL
        log.info("prowlarr.get_nzb_via_download_url", url=result.download_url[:80])
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, headers=headers) as c:
            resp = await c.get(result.download_url)
            resp.raise_for_status()
            content = resp.content
            if not content:
                raise RuntimeError("Download URL returned empty response")
            stripped = content.lstrip()
            if len(content) < 500 or not (stripped.startswith(b"<?xml") or stripped.startswith(b"<nzb")):
                log.warning("prowlarr.bad_nzb_content", bytes=len(content), preview=content[:200])
                raise RuntimeError(f"Download URL returned non-NZB content ({len(content)} bytes)")
            return content

    async def search(self, query: str) -> list[ProwlarrResult]:
        """
        Search all indexers via per-indexer Newznab API.
        Returns audio-only results sorted best-first.
        """
        indexers = await self._get_indexers()
        if not indexers:
            log.warning("prowlarr.no_indexers")
            return []

        # Map indexer_id → priority (lower = higher priority)
        indexer_priority: dict[int, int] = {ix["id"]: ix["priority"] for ix in indexers}

        all_items: list[tuple[int, ET.Element]] = []  # (indexer_id, item)
        async with httpx.AsyncClient(timeout=60.0) as c:
            for iid in [ix["id"] for ix in indexers]:
                url = f"{self._base}/{iid}/api"
                params = {"t": "search", "q": query, "apikey": self._api_key}
                try:
                    resp = await c.get(url, params=params)
                    resp.raise_for_status()
                    root = ET.fromstring(resp.text)
                    channel = root.find("channel")
                    if channel is not None:
                        for item in channel.findall("item"):
                            all_items.append((iid, item))
                except Exception as e:
                    log.warning("prowlarr.indexer_error", indexer_id=iid, error=str(e))

        log.info("prowlarr.raw_count", count=len(all_items), query=query)

        now = datetime.now(timezone.utc)
        results = []

        for iid, item in all_items:
            title = item.findtext("title") or ""
            download_url = item.findtext("link") or ""
            if not download_url:
                enc = item.find("enclosure")
                if enc is not None:
                    download_url = enc.get("url", "")
            if not download_url:
                continue

            # Extract GUID — strip URL prefix, just keep the ID value
            guid_raw = item.findtext("guid") or ""

            pub_date_str = item.findtext("pubDate") or ""
            age_days = 0.0
            if pub_date_str:
                try:
                    from email.utils import parsedate_to_datetime
                    published = parsedate_to_datetime(pub_date_str)
                    age_days = (now - published).total_seconds() / 86400
                except Exception:
                    pass

            size_str = item.findtext("size") or "0"
            try:
                size = int(size_str)
            except ValueError:
                size = 0

            cats = []
            for cat_el in item.findall("category"):
                try:
                    cats.append(int(cat_el.text or "0"))
                except ValueError:
                    pass
            for attr in item.findall(f"{{{_NEWZNAB_NS}}}attr"):
                if attr.get("name") == "category":
                    try:
                        cats.append(int(attr.get("value", "0")))
                    except ValueError:
                        pass

            grabs = 0
            for attr in item.findall(f"{{{_NEWZNAB_NS}}}attr"):
                if attr.get("name") == "grabs":
                    try:
                        grabs = int(attr.get("value", "0"))
                    except ValueError:
                        pass
                    break

            indexer_el = item.find("prowlarrindexer")
            indexer = indexer_el.text if indexer_el is not None else ""

            result = ProwlarrResult(
                title=title,
                download_url=download_url,
                guid=guid_raw,
                indexer_id=iid,
                size=size,
                indexer=indexer or "",
                age_days=age_days,
                grabs=grabs,
                categories=list(set(cats)),
            )

            if result.is_video:
                continue

            results.append(result)

        # Sort: Prowlarr priority first (lower = better), then by score descending
        results.sort(key=lambda r: (indexer_priority.get(r.indexer_id, 25), -r.score))
        log.info("prowlarr.filtered_count", count=len(results), query=query)
        if results:
            best = results[0]
            log.info("prowlarr.best_result", title=best.title, score=best.score, indexer=best.indexer)
        return results
