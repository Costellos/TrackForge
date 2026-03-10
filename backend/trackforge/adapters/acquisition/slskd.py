"""
slskd acquisition adapter.

Wraps the slskd REST API to search the Soulseek network and submit downloads.
slskd API base: {slskd_url}/api/v0/
Auth: X-API-Key header.
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from pathlib import PurePosixPath

import httpx


# ─────────────────────────────────────────────
# DATA TYPES
# ─────────────────────────────────────────────

@dataclass
class SlskdFile:
    username: str
    filename: str          # full path as seen on the remote user's share
    size: int
    bit_rate: int | None
    is_vbr: bool
    extension: str
    attributes: dict = field(default_factory=dict)

    @property
    def dirname(self) -> str:
        """Parent directory of the remote filename (used to group album files)."""
        return str(PurePosixPath(self.filename.replace("\\", "/")).parent)

    @property
    def format_score(self) -> int:
        """Higher is better. FLAC=3, MP3 320=2, MP3 other=1, else=0."""
        ext = self.extension.lower().lstrip(".")
        if ext == "flac":
            return 3
        if ext == "mp3":
            if self.bit_rate and self.bit_rate >= 320:
                return 2
            return 1
        return 0


@dataclass
class SlskdAlbumCandidate:
    """A group of files from the same remote directory — treated as one album release."""
    username: str
    directory: str
    files: list[SlskdFile]
    upload_speed: int = 0
    has_free_slot: bool = False

    @property
    def score(self) -> float:
        if not self.files:
            return 0.0
        format_score = max(f.format_score for f in self.files)
        slot_bonus = 1.0 if self.has_free_slot else 0.0
        speed_bonus = min(self.upload_speed / 1_000_000, 1.0)  # normalise to ~1Mbps
        return format_score * 10 + slot_bonus * 2 + speed_bonus


# ─────────────────────────────────────────────
# CLIENT
# ─────────────────────────────────────────────

class SlskdClient:
    def __init__(self, base_url: str, api_key: str):
        self._base = base_url.rstrip("/") + "/api/v0"
        self._headers = {"X-API-Key": api_key, "Content-Type": "application/json"}

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(headers=self._headers, timeout=30.0)

    async def health_check(self) -> bool:
        try:
            async with self._client() as c:
                r = await c.get(f"{self._base}/application")
                return r.status_code == 200
        except Exception:
            return False

    async def search(
        self,
        query: str,
        wait_seconds: int = 25,
        poll_interval: float = 2.0,
    ) -> tuple[str, list[SlskdAlbumCandidate]]:
        """
        Submit a search, wait for results, return (search_id, candidates).
        Candidates are grouped by remote directory and sorted best-first.
        """
        search_id = str(uuid.uuid4())

        async with self._client() as c:
            # Create search
            resp = await c.post(
                f"{self._base}/searches",
                json={"id": search_id, "searchText": query},
            )
            resp.raise_for_status()

            # Poll until complete or timeout
            elapsed = 0.0
            while elapsed < wait_seconds:
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval
                state = await c.get(f"{self._base}/searches/{search_id}")
                if state.status_code == 200 and state.json().get("isComplete"):
                    break

            # Fetch responses
            responses_resp = await c.get(f"{self._base}/searches/{search_id}/responses")
            if responses_resp.status_code != 200:
                return search_id, []

            responses = responses_resp.json()

        candidates = _parse_responses(responses)
        candidates.sort(key=lambda c: c.score, reverse=True)
        return search_id, candidates

    async def download(self, username: str, files: list[SlskdFile]) -> None:
        """Submit a batch of files from a single user for download."""
        payload = [{"filename": f.filename, "size": f.size} for f in files]
        async with self._client() as c:
            resp = await c.post(
                f"{self._base}/transfers/downloads/{username}",
                json=payload,
            )
            resp.raise_for_status()

    async def get_user_transfers(self, username: str) -> list[dict]:
        """Return raw transfer objects for a given username."""
        async with self._client() as c:
            resp = await c.get(f"{self._base}/transfers/downloads/{username}")
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            data = resp.json()
            # Response is a list of directory objects each with a files list
            transfers = []
            for directory in data:
                transfers.extend(directory.get("files", []))
            return transfers

    async def delete_search(self, search_id: str) -> None:
        async with self._client() as c:
            await c.delete(f"{self._base}/searches/{search_id}")


# ─────────────────────────────────────────────
# PARSING / SCORING
# ─────────────────────────────────────────────

def _parse_responses(responses: list[dict]) -> list[SlskdAlbumCandidate]:
    """Parse raw slskd search responses into grouped album candidates."""
    # Group by (username, directory)
    groups: dict[tuple[str, str], SlskdAlbumCandidate] = {}

    for response in responses:
        username = response.get("username", "")
        upload_speed = response.get("uploadSpeed", 0)
        has_free_slot = response.get("hasFreeUploadSlot", False)
        files_raw = response.get("files", [])

        for f_raw in files_raw:
            filename = f_raw.get("filename", "")
            ext = f_raw.get("extension", "") or PurePosixPath(filename.replace("\\", "/")).suffix.lstrip(".")
            slskd_file = SlskdFile(
                username=username,
                filename=filename,
                size=f_raw.get("size", 0),
                bit_rate=f_raw.get("bitRate"),
                is_vbr=f_raw.get("isVariableBitRate", False),
                extension=ext,
                attributes={a["type"]: a["value"] for a in f_raw.get("attributes", [])},
            )
            key = (username, slskd_file.dirname)
            if key not in groups:
                groups[key] = SlskdAlbumCandidate(
                    username=username,
                    directory=slskd_file.dirname,
                    files=[],
                    upload_speed=upload_speed,
                    has_free_slot=has_free_slot,
                )
            groups[key].files.append(slskd_file)

    # Filter to groups that look like music (at least one audio file)
    audio_exts = {"flac", "mp3", "ogg", "opus", "aac", "m4a", "wav", "aiff"}
    result = []
    for candidate in groups.values():
        audio_files = [f for f in candidate.files if f.extension.lower().lstrip(".") in audio_exts]
        if audio_files:
            candidate.files = audio_files
            result.append(candidate)

    return result
