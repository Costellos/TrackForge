"""
NZBGet download adapter.

Uses the NZBGet JSON-RPC API to submit NZB URLs and poll download status.
API endpoint: http://user:pass@host:port/jsonrpc
"""

import httpx
import structlog

log = structlog.get_logger()

# NZBGet download group statuses that mean "still going"
ACTIVE_STATUSES = {"QUEUED", "PAUSED", "DOWNLOADING", "FETCHING", "PP_QUEUED", "PP_EXECUTING"}
DONE_STATUSES = {"PP_FINISHED", "SUCCESS"}
FAILED_STATUSES = {"FAILED", "FAILURE", "DELETED"}


class NZBGetClient:
    def __init__(self, base_url: str, username: str, password: str):
        # base_url: e.g. "http://192.168.1.50:6789"
        parsed = base_url.rstrip("/")
        # Embed credentials into URL for Basic Auth via httpx
        self._rpc_url = parsed + "/jsonrpc"
        self._auth = (username, password) if username else None

    def _client(self) -> httpx.AsyncClient:
        kwargs: dict = {"timeout": 15.0}
        if self._auth:
            kwargs["auth"] = self._auth
        return httpx.AsyncClient(**kwargs)

    async def _call(self, method: str, params: list) -> object:
        payload = {"method": method, "params": params, "id": 1}
        async with self._client() as c:
            resp = await c.post(self._rpc_url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            log.info("nzbget.rpc", method=method, result=data)
            if data.get("error"):
                raise RuntimeError(f"NZBGet error: {data['error']}")
            return data.get("result")

    async def health_check(self) -> bool:
        try:
            result = await self._call("version", [])
            log.info("nzbget.version", version=result)
            return bool(result)
        except Exception:
            return False

    async def append(self, name: str, nzb_url: str, category: str = "") -> int:
        """
        Submit an NZB URL to NZBGet for download.
        NZBGet fetches the NZB file itself from the URL.
        Returns the NZBGet internal ID (NZBID), or -1 on failure.
        """
        log.info("nzbget.append", name=name, category=category, url=nzb_url[:80])

        # NZBGet JSON-RPC append (10 params, compatible with v16–v25.4):
        # NZBFilename, NZBContent, Category, Priority, AddToTop, AddPaused,
        # DupeKey, DupeScore, DupeMode, Parameters
        # When NZBContent starts with http://, NZBGet fetches it as a URL.
        result = await self._call("append", [
            name + ".nzb",  # NZBFilename
            nzb_url,        # NZBContent — NZBGet treats http:// as URL to fetch
            category,       # Category
            0,              # Priority (0 = normal)
            False,          # AddToTop
            False,          # AddPaused
            "",             # DupeKey
            0,              # DupeScore
            "SCORE",        # DupeMode
            None,           # Parameters (null = use defaults)
        ])
        nzbid = int(result)
        log.info("nzbget.appended", nzbid=nzbid, name=name)
        return nzbid

    async def get_group(self, nzbid: int) -> dict | None:
        """
        Return the download group for a given NZBID, or None if not found.
        Checks active queue first, then history (completed jobs leave the queue).
        """
        result = await self._call("listgroups", [0])
        if isinstance(result, list):
            for group in result:
                if group.get("NZBID") == nzbid:
                    return group

        # Not in active queue — check history
        history = await self._call("history", [False])
        if isinstance(history, list):
            for item in history:
                if item.get("NZBID") == nzbid:
                    return item

        return None

    async def get_status(self, nzbid: int) -> str | None:
        """
        Return the status string for a download, or None if not found.
        Active queue values: QUEUED, PAUSED, DOWNLOADING, FETCHING,
                             PP_QUEUED, PP_EXECUTING, PP_FINISHED, FAILED, DELETED
        History values: SUCCESS, FAILURE, DELETED
        """
        group = await self.get_group(nzbid)
        if not group:
            return None
        # History items use "Status" too but with different values (SUCCESS/FAILURE)
        return group.get("Status")

    async def get_progress(self, nzbid: int) -> tuple[int, int]:
        """Return (bytes_downloaded, bytes_total) for a download."""
        group = await self.get_group(nzbid)
        if not group:
            return 0, 0
        total_mb = group.get("FileSizeMB", 0)
        remaining_mb = group.get("RemainingSizeMB", 0)
        downloaded_mb = total_mb - remaining_mb
        return downloaded_mb * 1024 * 1024, total_mb * 1024 * 1024
