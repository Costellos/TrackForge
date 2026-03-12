"""
Import pipeline v2.

Scans downloaded audio files, creates MediaAsset + ImportCandidate records,
runs match scoring against expected versions from the request target,
and auto-approves high-confidence matches.

Gated behind the ``import_pipeline_v2`` setting (default false).
When disabled, the existing simple flow in processing_service continues unchanged.
"""

import hashlib
import os
import uuid
from pathlib import Path

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from trackforge.db.models import (
    AcquisitionJob,
    ArtistCredit,
    Collection,
    ImportCandidate,
    MediaAsset,
    Request,
    Song,
    Version,
    VersionCollectionEntry,
    VersionTrait,
)
from trackforge.domain.services.match_scoring import (
    MatchCandidate,
    MatchTarget,
    score_match,
    THRESHOLD_AUTO_ACCEPT,
)
from trackforge.domain.services.trait_parser import parse_traits

log = structlog.get_logger()

AUDIO_EXTENSIONS = {".flac", ".mp3", ".m4a", ".ogg", ".opus", ".wma", ".wav", ".aac", ".alac"}


def _file_checksum(path: str, algo: str = "sha256") -> str:
    """Compute hex digest of a file."""
    h = hashlib.new(algo)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_audio_metadata(filepath: str) -> dict:
    """Read audio metadata using mutagen. Returns dict with tags and technical info."""
    try:
        from mutagen import File as MutagenFile
    except ImportError:
        return {}

    try:
        audio = MutagenFile(filepath, easy=True)
    except Exception:
        return {}

    if audio is None:
        return {}

    def first_tag(key: str) -> str:
        val = audio.get(key)
        if isinstance(val, list) and val:
            return str(val[0])
        if val is not None:
            return str(val)
        return ""

    tags = {}
    for key in ["artist", "albumartist", "album", "title", "tracknumber", "date", "genre"]:
        tags[key] = first_tag(key)

    info = {
        "tags": tags,
        "duration_ms": int(audio.info.length * 1000) if audio.info and audio.info.length else None,
        "bitrate": getattr(audio.info, "bitrate", None),
        "sample_rate": getattr(audio.info, "sample_rate", None),
        "channels": getattr(audio.info, "channels", None),
    }

    # Try to get bit depth (FLAC-specific)
    bit_depth = getattr(audio.info, "bits_per_sample", None)
    if bit_depth:
        info["bit_depth"] = bit_depth

    return info


async def scan_and_create_assets(
    db: AsyncSession,
    folder: str,
    job: AcquisitionJob,
) -> list[MediaAsset]:
    """
    Scan audio files in *folder*, create MediaAsset records for each.
    Returns the list of created MediaAsset records.
    """
    assets = []

    if not os.path.isdir(folder):
        log.warning("import.folder_not_found", folder=folder)
        return assets

    for entry in sorted(os.scandir(folder), key=lambda e: e.name):
        if not entry.is_file():
            continue
        ext = Path(entry.name).suffix.lower()
        if ext not in AUDIO_EXTENSIONS:
            continue

        # Check if we already have a MediaAsset for this path
        existing = await db.execute(
            select(MediaAsset).where(MediaAsset.file_path == entry.path)
        )
        if existing.scalar_one_or_none():
            continue

        meta = _read_audio_metadata(entry.path)
        tags = meta.get("tags", {})

        checksum = _file_checksum(entry.path)

        asset = MediaAsset(
            id=str(uuid.uuid4()),
            file_path=entry.path,
            file_size=entry.stat().st_size,
            format=ext.lstrip("."),
            bitrate=meta.get("bitrate"),
            sample_rate=meta.get("sample_rate"),
            bit_depth=meta.get("bit_depth"),
            channels=meta.get("channels"),
            duration_ms=meta.get("duration_ms"),
            checksum=checksum,
            raw_tags=tags,
            match_state="unmatched",
        )
        db.add(asset)
        assets.append(asset)

    if assets:
        await db.flush()
        log.info("import.assets_created", count=len(assets), folder=folder)

    return assets


async def create_import_candidates(
    db: AsyncSession,
    assets: list[MediaAsset],
    job: AcquisitionJob,
) -> list[ImportCandidate]:
    """Create ImportCandidate records for each MediaAsset, linked to the acquisition job."""
    candidates = []
    for asset in assets:
        candidate = ImportCandidate(
            id=str(uuid.uuid4()),
            media_asset_id=asset.id,
            acquisition_job_id=job.id,
            stage="staged",
        )
        db.add(candidate)
        candidates.append(candidate)

    if candidates:
        await db.flush()

    return candidates


async def _build_targets_for_collection(
    db: AsyncSession,
    collection_id: str,
) -> list[MatchTarget]:
    """Build MatchTarget list from a collection's versions."""
    result = await db.execute(
        select(VersionCollectionEntry)
        .options(
            selectinload(VersionCollectionEntry.version)
            .selectinload(Version.song),
            selectinload(VersionCollectionEntry.version)
            .selectinload(Version.traits),
        )
        .where(VersionCollectionEntry.collection_id == collection_id)
        .order_by(VersionCollectionEntry.disc_number, VersionCollectionEntry.track_number)
    )
    entries = result.scalars().all()

    targets = []
    for entry in entries:
        version = entry.version
        if not version:
            continue

        song = version.song
        title = version.title_override or (song.title if song else "")
        artist = ""

        # Get artist from song's credits
        if song:
            credit_result = await db.execute(
                select(ArtistCredit)
                .options(selectinload(ArtistCredit.artist))
                .where(ArtistCredit.song_id == song.id, ArtistCredit.role == "primary")
            )
            credit = credit_result.scalars().first()
            if credit and credit.artist:
                artist = credit.artist.name

        trait_names = [t.name for t in (version.traits or [])]

        year = None
        if version.recording_date:
            year = version.recording_date.year

        targets.append(MatchTarget(
            artist=artist,
            title=title,
            duration_ms=version.duration_ms,
            year=year,
            traits=trait_names,
        ))

    return targets


async def _build_targets_for_song(
    db: AsyncSession,
    song_id: str,
) -> list[MatchTarget]:
    """Build MatchTarget list from a song's versions."""
    result = await db.execute(
        select(Version)
        .options(selectinload(Version.song), selectinload(Version.traits))
        .where(Version.song_id == song_id)
    )
    versions = result.scalars().all()

    targets = []
    for version in versions:
        song = version.song
        title = version.title_override or (song.title if song else "")
        artist = ""

        if song:
            credit_result = await db.execute(
                select(ArtistCredit)
                .options(selectinload(ArtistCredit.artist))
                .where(ArtistCredit.song_id == song.id, ArtistCredit.role == "primary")
            )
            credit = credit_result.scalars().first()
            if credit and credit.artist:
                artist = credit.artist.name

        trait_names = [t.name for t in (version.traits or [])]

        targets.append(MatchTarget(
            artist=artist,
            title=title,
            duration_ms=version.duration_ms,
            traits=trait_names,
        ))

    return targets


async def run_matching(
    db: AsyncSession,
    candidates: list[ImportCandidate],
    req: Request,
) -> int:
    """
    Run match scoring for each ImportCandidate against the request's target versions.
    Updates candidate stage and MediaAsset match_state/confidence.
    Returns number of auto-approved matches.
    """
    # Build targets from request target
    if req.target_type == "collection":
        targets = await _build_targets_for_collection(db, req.target_id)
    elif req.target_type == "song":
        targets = await _build_targets_for_song(db, req.target_id)
    else:
        log.warning("import.unsupported_target_type", target_type=req.target_type)
        return 0

    if not targets:
        log.warning("import.no_targets", request_id=req.id, target_type=req.target_type)
        # Advance all candidates to awaiting_review with no match data
        for ic in candidates:
            ic.stage = "awaiting_review"
        await db.flush()
        return 0

    auto_approved = 0

    for ic in candidates:
        asset = await db.get(MediaAsset, ic.media_asset_id)
        if not asset:
            continue

        tags = asset.raw_tags or {}
        file_title = tags.get("title", Path(asset.file_path).stem)
        file_artist = tags.get("artist", "")

        # Parse traits from file title
        clean_title, file_traits = parse_traits(file_title)

        # Build candidate from file tags
        match_candidate = MatchCandidate(
            artist=file_artist,
            title=clean_title,
            duration_ms=asset.duration_ms,
            raw_title=file_title,
        )

        # Try to extract year from date tag
        date_tag = tags.get("date", "")
        if date_tag:
            try:
                match_candidate.year = int(date_tag[:4])
            except (ValueError, IndexError):
                pass

        # Score against all targets, take best match
        best_result = None
        best_target_idx = -1
        for idx, target in enumerate(targets):
            result = score_match(target, match_candidate)
            if best_result is None or result.total_score > best_result.total_score:
                best_result = result
                best_target_idx = idx

        # Store match results
        match_data = {
            "best_score": best_result.total_score if best_result else 0,
            "decision": best_result.decision if best_result else "reject",
            "components": best_result.components if best_result else {},
            "matched_target_index": best_target_idx,
            "file_tags": tags,
        }
        ic.candidates = [match_data]

        # Update MediaAsset
        if best_result:
            asset.match_confidence = best_result.total_score

            if best_result.total_score >= THRESHOLD_AUTO_ACCEPT:
                asset.match_state = "matched"
                ic.stage = "approved"
                auto_approved += 1

                # Auto-link: set version_id on the MediaAsset
                if req.target_type == "collection" and best_target_idx >= 0:
                    # Get the version from the collection entry at that index
                    entry_result = await db.execute(
                        select(VersionCollectionEntry)
                        .where(VersionCollectionEntry.collection_id == req.target_id)
                        .order_by(VersionCollectionEntry.disc_number, VersionCollectionEntry.track_number)
                        .offset(best_target_idx)
                        .limit(1)
                    )
                    entry = entry_result.scalars().first()
                    if entry:
                        asset.version_id = entry.version_id
                        ic.selected_version_id = entry.version_id
                elif req.target_type == "song" and best_target_idx >= 0:
                    versions_result = await db.execute(
                        select(Version)
                        .where(Version.song_id == req.target_id)
                    )
                    versions = versions_result.scalars().all()
                    if best_target_idx < len(versions):
                        asset.version_id = versions[best_target_idx].id
                        ic.selected_version_id = versions[best_target_idx].id

                log.info(
                    "import.auto_approved",
                    asset_id=asset.id,
                    score=best_result.total_score,
                    version_id=asset.version_id,
                )
            else:
                asset.match_state = "needs_review" if best_result.total_score >= 0.70 else "candidate"
                ic.stage = "awaiting_review"
                log.info(
                    "import.needs_review",
                    asset_id=asset.id,
                    score=best_result.total_score,
                    decision=best_result.decision,
                )
        else:
            asset.match_state = "unmatched"
            ic.stage = "awaiting_review"

    await db.flush()
    return auto_approved


async def process_import_pipeline(
    db: AsyncSession,
    req: Request,
    job: AcquisitionJob,
    library_path: str,
) -> dict:
    """
    Full v2 import pipeline for a single request:
    1. Scan audio files → create MediaAsset records
    2. Create ImportCandidate records
    3. Run match scoring
    4. Return summary

    Called from processing_service when import_pipeline_v2 is enabled.
    """
    log.info("import.pipeline_start", request_id=req.id, library_path=library_path)

    # Step 1: Scan and create assets
    assets = await scan_and_create_assets(db, library_path, job)
    if not assets:
        log.warning("import.no_audio_files", request_id=req.id, library_path=library_path)
        return {"assets": 0, "candidates": 0, "auto_approved": 0}

    # Step 2: Create import candidates
    candidates = await create_import_candidates(db, assets, job)

    # Step 3: Run matching
    auto_approved = await run_matching(db, candidates, req)

    total = len(candidates)
    log.info(
        "import.pipeline_complete",
        request_id=req.id,
        assets=len(assets),
        candidates=total,
        auto_approved=auto_approved,
        needs_review=total - auto_approved,
    )

    return {
        "assets": len(assets),
        "candidates": total,
        "auto_approved": auto_approved,
    }
