"""
Processing service.

Handles requests in the `processing` state:
  1. Looks up where NZBGet put the files (DestDir from history API)
  2. Moves the folder into the library path
  3. Triggers a Jellyfin library scan
  4. Marks the request as `available`
"""

import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from trackforge.config import get_settings
from trackforge.db.models import AcquisitionJob, Collection, ExternalIdentifier, Request
from trackforge.domain.services.notification_service import notify_request_status
from trackforge.domain.services.settings_service import get_setting

log = structlog.get_logger()
settings = get_settings()


async def process_processing_requests(db: AsyncSession) -> int:
    """
    Find all `processing` requests, move their downloaded files to the
    library, trigger a Jellyfin scan, and advance status to `available`.
    """
    result = await db.execute(select(Request).where(Request.status == "processing"))
    requests = result.scalars().all()
    if not requests:
        return 0

    processed = 0
    for req in requests:
        job_result = await db.execute(
            select(AcquisitionJob).where(
                AcquisitionJob.request_id == req.id,
                AcquisitionJob.status == "completed",
            )
        )
        job = job_result.scalars().first()
        if not job:
            continue

        if job.adapter == "nzbget":
            moved_path = await _move_nzbget_download(db, req, job)
        else:
            log.info("processing.adapter_not_supported", adapter=job.adapter, job_id=job.id)
            continue

        if moved_path:
            req.status = "available"
            req.resolved_at = datetime.now(timezone.utc)
            req.updated_at = datetime.now(timezone.utc)
            # Store the library path for Jellyfin matching later
            params = req.search_params or {}
            params["library_path"] = moved_path
            req.search_params = params
            processed += 1
            log.info("processing.complete", request_id=req.id, library_path=moved_path)

    if processed:
        await db.commit()
        await _trigger_jellyfin_scan()
        # Notify for each newly available request
        for req in requests:
            if req.status == "available":
                await notify_request_status(db, req)

    return processed


def _sanitize_path(name: str) -> str:
    """Remove characters that are unsafe in file/directory names."""
    return re.sub(r'[<>:"/\\|?*]', "", name).strip().rstrip(".")


async def _resolve_artist_name(db: AsyncSession, collection: Collection) -> str | None:
    """Try to resolve artist name from MusicBrainz when collection has no primary_artist."""
    from trackforge.adapters.metadata import musicbrainz as mb

    result = await db.execute(
        select(ExternalIdentifier).where(
            ExternalIdentifier.entity_type == "collection",
            ExternalIdentifier.entity_id == collection.id,
            ExternalIdentifier.provider == "musicbrainz",
        )
    )
    ext = result.scalar_one_or_none()
    if not ext:
        log.warning("processing.no_external_id_for_collection", collection_id=collection.id)
        return None

    try:
        log.info("processing.resolving_artist_from_mb", mbid=ext.external_id, collection_id=collection.id)
        rg = await mb.get_release_group(ext.external_id)
        if rg and rg.get("artists"):
            name = rg["artists"][0].get("name")
            log.info("processing.resolved_artist", name=name, mbid=ext.external_id)
            return name
        log.warning("processing.no_artists_in_rg", mbid=ext.external_id, rg_keys=list(rg.keys()) if rg else None)
    except Exception as e:
        log.warning("processing.artist_resolve_exception", collection_id=collection.id, error=str(e))

    return None


async def _build_library_path(db: AsyncSession, req: Request) -> str | None:
    """
    Build the destination folder path using the library_folder_pattern setting.
    Returns the full path, or None if metadata is insufficient (falls back to original name).
    """
    if req.target_type != "collection":
        return None

    result = await db.execute(
        select(Collection)
        .options(selectinload(Collection.primary_artist))
        .where(Collection.id == req.target_id)
    )
    collection = result.scalars().first()
    if not collection:
        return None

    artist_name = "Unknown Artist"
    if collection.primary_artist:
        artist_name = collection.primary_artist.name
    else:
        log.warning(
            "processing.no_primary_artist",
            collection_id=collection.id,
            collection_title=collection.title,
            primary_artist_id=collection.primary_artist_id,
        )
        # Fallback 1: check request.search_params for artist_name
        search_artist = (req.search_params or {}).get("artist_name")
        if search_artist:
            artist_name = search_artist
            log.info("processing.artist_from_search_params", artist=search_artist, collection_id=collection.id)
        else:
            # Fallback 2: look up artist from MusicBrainz via the collection's external ID
            resolved = await _resolve_artist_name(db, collection)
            if resolved:
                artist_name = resolved
                log.info("processing.artist_resolved_from_mb", artist=resolved, collection_id=collection.id)
            else:
                log.error("processing.artist_resolve_failed_using_unknown", collection_id=collection.id)

    album_title = collection.title or "Unknown Album"
    year = ""
    if collection.release_date:
        year = str(collection.release_date.year)

    pattern = await get_setting(db, "library_folder_pattern")
    folder = pattern.format(
        artist=_sanitize_path(artist_name),
        album=_sanitize_path(album_title),
        year=year,
    )
    # Clean up empty brackets if year is missing
    folder = re.sub(r'\s*\[\s*\]', '', folder)
    folder = re.sub(r'\s*\(\s*\)', '', folder)
    folder = folder.strip()

    return os.path.join(settings.library_path, folder)


async def _move_nzbget_download(db: AsyncSession, req: Request, job: AcquisitionJob) -> str | None:
    """
    Look up the NZBGet DestDir for this job and move the folder into the library.
    Uses library_folder_pattern to name the destination folder.
    Returns the destination path if the files are in the library, or None on failure.
    """
    from trackforge.adapters.acquisition.nzbget import NZBGetClient

    if not job.external_id:
        log.warning("processing.no_external_id", job_id=job.id)
        return None

    if not settings.nzbget_complete_path:
        log.warning(
            "processing.nzbget_complete_path_not_set",
            msg="Set NZBGET_COMPLETE_PATH in env to enable file moving",
            job_id=job.id,
        )
        return None

    nzbget = NZBGetClient(settings.nzbget_url, settings.nzbget_username, settings.nzbget_password)
    try:
        nzbid = int(job.external_id)
        group = await nzbget.get_group(nzbid)
    except Exception as e:
        log.error("processing.nzbget_lookup_failed", job_id=job.id, error=str(e))
        return None

    if not group:
        log.warning("processing.nzbget_group_not_found", job_id=job.id, nzbid=job.external_id)
        return None

    # FinalDir is set if a post-processing script moved the files; fall back to DestDir
    dest_dir = group.get("FinalDir") or group.get("DestDir")
    if not dest_dir:
        log.warning("processing.no_dest_dir", job_id=job.id)
        return None

    # Map NZBGet's reported path to the container-mounted path.
    folder_name = os.path.basename(dest_dir.rstrip("/"))
    src_path = os.path.join(settings.nzbget_complete_path, folder_name)

    # Build destination path from pattern, fall back to original folder name
    dst_path = await _build_library_path(db, req)
    if not dst_path:
        dst_path = os.path.join(settings.library_path, folder_name)

    if os.path.exists(dst_path):
        log.info("processing.already_in_library", dst=dst_path, job_id=job.id)
        await _rename_files_in_folder(db, dst_path)
        return dst_path

    if not os.path.exists(src_path):
        log.warning("processing.source_not_found", src=src_path, job_id=job.id)
        return None

    # Ensure parent directories exist (e.g. Artist/ subfolder)
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)

    try:
        shutil.move(src_path, dst_path)
        log.info("processing.moved", src=src_path, dst=dst_path, job_id=job.id)
        _fix_ownership(dst_path)
        await _rename_files_in_folder(db, dst_path)
        return dst_path
    except Exception as e:
        log.error("processing.move_failed", src=src_path, dst=dst_path, error=str(e), job_id=job.id)
        return None


MEDIA_UID = 1000  # couchdaddy
MEDIA_GID = 1000  # couchdaddy


def _fix_ownership(path: str) -> None:
    """Set ownership to couchdaddy:couchdaddy (1000:1000) with group read/write on moved files."""
    try:
        os.chown(path, MEDIA_UID, MEDIA_GID)
        os.chmod(path, 0o775)
        for root, dirs, files in os.walk(path):
            for d in dirs:
                dp = os.path.join(root, d)
                os.chown(dp, MEDIA_UID, MEDIA_GID)
                os.chmod(dp, 0o775)
            for f in files:
                fp = os.path.join(root, f)
                os.chown(fp, MEDIA_UID, MEDIA_GID)
                os.chmod(fp, 0o664)
    except Exception as e:
        log.warning("processing.chown_failed", path=path, error=str(e))


AUDIO_EXTENSIONS = {".flac", ".mp3", ".m4a", ".ogg", ".opus", ".wma", ".wav", ".aac", ".alac"}


async def _rename_files_in_folder(db: AsyncSession, folder: str) -> None:
    """
    Rename audio files in *folder* using the file_naming_pattern setting.
    Reads ID3/FLAC/etc. tags via mutagen to fill {track}, {artist}, {title}.
    """
    try:
        from mutagen import File as MutagenFile
    except ImportError:
        log.warning("processing.mutagen_not_installed", msg="Skipping file rename")
        return

    pattern = await get_setting(db, "file_naming_pattern")
    if not pattern:
        return

    for entry in os.scandir(folder):
        if not entry.is_file():
            continue
        ext = Path(entry.name).suffix.lower()
        if ext not in AUDIO_EXTENSIONS:
            continue

        try:
            audio = MutagenFile(entry.path, easy=True)
        except Exception:
            log.debug("processing.tag_read_failed", file=entry.name)
            continue

        if audio is None:
            continue

        title = _first_tag(audio, "title") or Path(entry.name).stem
        artist = _first_tag(audio, "artist") or "Unknown Artist"
        track = _first_tag(audio, "tracknumber") or "00"
        # Normalize track number — strip "/total" suffix (e.g. "3/12" → "03")
        track = track.split("/")[0].strip().zfill(2)

        new_stem = pattern.format(
            track=_sanitize_path(track),
            artist=_sanitize_path(artist),
            title=_sanitize_path(title),
        )
        new_name = new_stem + ext
        new_path = os.path.join(folder, new_name)

        if new_path == entry.path:
            continue

        # Avoid overwriting an existing file
        if os.path.exists(new_path):
            log.debug("processing.rename_skip_exists", file=new_name)
            continue

        try:
            os.rename(entry.path, new_path)
            log.debug("processing.file_renamed", old=entry.name, new=new_name)
        except Exception as e:
            log.warning("processing.rename_failed", file=entry.name, error=str(e))


def _first_tag(audio: dict, key: str) -> str:
    """Get the first value from a mutagen tag list, or empty string."""
    val = audio.get(key)
    if isinstance(val, list) and val:
        return str(val[0])
    if val is not None:
        return str(val)
    return ""


async def _trigger_jellyfin_scan() -> None:
    if not settings.jellyfin_url or not settings.jellyfin_api_key:
        log.info("processing.jellyfin_not_configured", msg="Skipping scan trigger")
        return

    from trackforge.adapters.library.jellyfin import JellyfinClient

    client = JellyfinClient(settings.jellyfin_url, settings.jellyfin_api_key)
    try:
        await client.trigger_scan()
    except Exception as e:
        log.warning("jellyfin.scan_failed", error=str(e))
