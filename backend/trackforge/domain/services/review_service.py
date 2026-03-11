"""
Tag review service.

Reads and writes audio file tags (via mutagen) for requests in pending_review state.
Also handles the auto-import timer for unreviewed requests.
"""

import os
from datetime import datetime, timezone
from pathlib import Path

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from trackforge.db.models import Request
from trackforge.domain.services.processing_service import finalize_import
from trackforge.domain.services.settings_service import get_setting, get_setting_bool

log = structlog.get_logger()

AUDIO_EXTENSIONS = {".flac", ".mp3", ".m4a", ".ogg", ".opus", ".wma", ".wav", ".aac", ".alac"}

# Tags we expose for review/editing
TAG_KEYS = ["artist", "albumartist", "album", "title", "tracknumber", "date", "genre"]


def _first_tag(audio, key: str) -> str:
    """Get the first value from a mutagen tag list, or empty string."""
    val = audio.get(key)
    if isinstance(val, list) and val:
        return str(val[0])
    if val is not None:
        return str(val)
    return ""


def read_tags(library_path: str) -> list[dict]:
    """
    Read audio file tags from a library folder.
    Returns a list of dicts with filename, tags, format, and duration.
    """
    try:
        from mutagen import File as MutagenFile
    except ImportError:
        log.warning("review.mutagen_not_installed")
        return []

    if not os.path.isdir(library_path):
        log.warning("review.path_not_found", path=library_path)
        return []

    files = []
    for entry in sorted(os.scandir(library_path), key=lambda e: e.name):
        if not entry.is_file():
            continue
        ext = Path(entry.name).suffix.lower()
        if ext not in AUDIO_EXTENSIONS:
            continue

        try:
            audio = MutagenFile(entry.path, easy=True)
        except Exception:
            log.debug("review.tag_read_failed", file=entry.name)
            continue

        if audio is None:
            continue

        tags = {}
        for key in TAG_KEYS:
            tags[key] = _first_tag(audio, key)

        duration_ms = int(audio.info.length * 1000) if audio.info and audio.info.length else None

        files.append({
            "filename": entry.name,
            "tags": tags,
            "format": ext.lstrip("."),
            "duration_ms": duration_ms,
        })

    return files


def write_tags(library_path: str, file_edits: list[dict]) -> int:
    """
    Write tag edits to audio files.
    file_edits is a list of {"filename": "...", "tags": {"artist": "...", ...}}
    Returns the number of files updated.
    """
    try:
        from mutagen import File as MutagenFile
    except ImportError:
        log.warning("review.mutagen_not_installed")
        return 0

    if not os.path.isdir(library_path):
        return 0

    updated = 0
    for edit in file_edits:
        filename = edit.get("filename", "")
        tags = edit.get("tags", {})
        if not filename or not tags:
            continue

        filepath = os.path.join(library_path, filename)
        if not os.path.isfile(filepath):
            log.warning("review.file_not_found", file=filename)
            continue

        try:
            audio = MutagenFile(filepath, easy=True)
            if audio is None:
                continue

            for key, value in tags.items():
                if key in TAG_KEYS and value is not None:
                    audio[key] = value

            audio.save()
            updated += 1
            log.info("review.tags_written", file=filename, tags=list(tags.keys()))
        except Exception as e:
            log.warning("review.tag_write_failed", file=filename, error=str(e))

    return updated


async def auto_import_pending_reviews(db: AsyncSession) -> int:
    """
    Check for pending_review requests that have exceeded the timeout
    and auto-import them. Returns the number auto-imported.
    """
    auto_import_enabled = await get_setting_bool(db, "tag_review_auto_import")
    if not auto_import_enabled:
        return 0

    timeout_str = await get_setting(db, "tag_review_timeout_minutes")
    timeout_minutes = max(1, int(timeout_str or "5"))

    result = await db.execute(
        select(Request).where(Request.status == "pending_review")
    )
    pending = result.scalars().all()
    if not pending:
        return 0

    now = datetime.now(timezone.utc)
    imported = 0

    for req in pending:
        params = req.search_params or {}
        review_at_str = params.get("pending_review_at")
        if not review_at_str:
            # No timestamp — set it now and skip this cycle
            params["pending_review_at"] = now.isoformat()
            req.search_params = params
            continue

        review_at = datetime.fromisoformat(review_at_str)
        if review_at.tzinfo is None:
            review_at = review_at.replace(tzinfo=timezone.utc)

        elapsed_minutes = (now - review_at).total_seconds() / 60
        if elapsed_minutes >= timeout_minutes:
            log.info(
                "review.auto_import",
                request_id=req.id,
                elapsed_minutes=round(elapsed_minutes, 1),
            )
            await finalize_import(db, req)
            imported += 1

    if not imported:
        await db.commit()

    return imported
