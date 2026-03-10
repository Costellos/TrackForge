"""
Acquisition service.

Orchestrates the lifecycle from approved Request → AcquisitionJob → download.

Supported pipelines (in priority order):
  1. Prowlarr (search) + NZBGet (download)  — adapter="nzbget"
  2. slskd (search + download)              — adapter="slskd"

State machine:
  Request:  approved → searching → downloading → processing
  AcqJob:   queued   → submitted → downloading → completed | failed
"""

import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from trackforge.config import get_settings
from trackforge.db.models import AcquisitionJob, Artist, ArtistCredit, Collection, Request, Song
from trackforge.domain.services.notification_service import notify_request_status

log = structlog.get_logger()
settings = get_settings()


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _active_adapter() -> str | None:
    """Return the adapter to use, or None if nothing is configured."""
    if settings.prowlarr_url and settings.prowlarr_api_key and settings.nzbget_url:
        return "nzbget"
    if settings.slskd_url and settings.slskd_api_key:
        return "slskd"
    return None


import re as _re

_SPECIAL_CHARS = _re.compile(r"[!\"#$%&'()*+,/:;<=>?@\[\\\]^_`{|}~]")


def _sanitize_query(q: str) -> str:
    """Strip Newznab special characters that break indexer searches (e.g. '!' is NOT operator)."""
    q = _SPECIAL_CHARS.sub(" ", q)
    return " ".join(q.split())  # collapse whitespace


def _build_query(target_type: str, name: str, artist_name: str | None) -> str:
    if target_type in ("collection", "song"):
        raw = f"{artist_name} {name}" if artist_name else name
        return _sanitize_query(raw)
    return _sanitize_query(name)


async def _resolve_name(db: AsyncSession, request: Request) -> tuple[str, str | None]:
    """Return (name, artist_name) for a request target."""
    if request.target_type == "artist":
        artist = await db.get(Artist, request.target_id)
        return (artist.name if artist else request.target_id), None

    if request.target_type == "collection":
        col = await db.get(Collection, request.target_id)
        if not col:
            return request.target_id, None
        artist_name = None
        if col.primary_artist_id:
            artist = await db.get(Artist, col.primary_artist_id)
            if artist:
                artist_name = artist.name
        return col.title, artist_name

    if request.target_type == "song":
        song = await db.get(Song, request.target_id)
        if not song:
            return request.target_id, None
        # Find primary artist from credits
        credit_result = await db.execute(
            select(ArtistCredit).where(
                ArtistCredit.song_id == song.id,
                ArtistCredit.role == "primary",
            ).order_by(ArtistCredit.position)
        )
        credit = credit_result.scalar_one_or_none()
        artist_name = None
        if credit:
            artist = await db.get(Artist, credit.artist_id)
            if artist:
                artist_name = artist.name
        return song.title, artist_name

    return request.target_id, None


# ─────────────────────────────────────────────
# DISPATCH APPROVED REQUESTS
# ─────────────────────────────────────────────

async def dispatch_approved_requests(db: AsyncSession) -> int:
    """
    Find all `approved` requests that don't yet have an active acquisition job,
    create AcquisitionJob records, and return the count.
    """
    adapter = _active_adapter()
    if not adapter:
        log.warning("acquisition.not_configured", msg="No acquisition adapter configured")
        return 0

    result = await db.execute(select(Request).where(Request.status == "approved"))
    requests = result.scalars().all()
    if not requests:
        return 0

    live_statuses = ("queued", "submitted", "downloading")
    result2 = await db.execute(
        select(AcquisitionJob.request_id).where(
            AcquisitionJob.request_id.in_([r.id for r in requests]),
            AcquisitionJob.status.in_(live_statuses),
        )
    )
    already_running = {row[0] for row in result2.all()}

    dispatched = 0
    for req in requests:
        if req.id in already_running:
            continue
        job = AcquisitionJob(
            id=str(uuid.uuid4()),
            request_id=req.id,
            adapter=adapter,
            status="queued",
        )
        db.add(job)
        req.status = "searching"
        req.updated_at = datetime.now(timezone.utc)
        dispatched += 1
        log.info("acquisition.dispatched", request_id=req.id, adapter=adapter)

    if dispatched:
        await db.commit()
    return dispatched


# ─────────────────────────────────────────────
# RUN QUEUED JOBS
# ─────────────────────────────────────────────

async def run_queued_jobs(db: AsyncSession) -> int:
    """Pick up queued jobs and execute the search + submit phase."""
    result = await db.execute(select(AcquisitionJob).where(AcquisitionJob.status == "queued"))
    jobs = result.scalars().all()
    if not jobs:
        return 0

    processed = 0
    for job in jobs:
        req = await db.get(Request, job.request_id)
        if not req:
            continue

        if job.adapter == "nzbget":
            await _run_nzbget_job(db, job, req)
        elif job.adapter == "slskd":
            await _run_slskd_job(db, job, req)

        processed += 1

    return processed


async def _run_nzbget_job(db: AsyncSession, job: AcquisitionJob, req: Request) -> None:
    """Search Prowlarr, pick best result, push NZB to NZBGet."""
    from trackforge.adapters.acquisition.prowlarr import ProwlarrClient
    from trackforge.adapters.acquisition.nzbget import NZBGetClient

    prowlarr = ProwlarrClient(settings.prowlarr_url, settings.prowlarr_api_key)
    nzbget = NZBGetClient(settings.nzbget_url, settings.nzbget_username, settings.nzbget_password)

    if not await prowlarr.health_check():
        log.warning("prowlarr.unreachable", url=settings.prowlarr_url)
        return

    if not await nzbget.health_check():
        log.warning("nzbget.unreachable", url=settings.nzbget_url)
        return

    name, artist_name = await _resolve_name(db, req)
    query = _build_query(req.target_type, name, artist_name)

    job.status = "submitted"
    job.source_query = query
    job.started_at = datetime.now(timezone.utc)
    job.updated_at = datetime.now(timezone.utc)
    await db.commit()

    log.info("prowlarr.searching", query=query, job_id=job.id)

    try:
        results = await prowlarr.search(query)

        # Exclude URLs already tried by previous failed/cancelled jobs for this request
        tried_result = await db.execute(
            select(AcquisitionJob.source_url).where(
                AcquisitionJob.request_id == req.id,
                AcquisitionJob.source_url.isnot(None),
                AcquisitionJob.status.in_(["failed", "cancelled"]),
            )
        )
        tried_urls = {row[0] for row in tried_result.all()}
        if tried_urls:
            results = [r for r in results if r.download_url not in tried_urls]
            log.info("acquisition.filtered_tried", excluded=len(tried_urls), remaining=len(results), job_id=job.id)

        if not results:
            log.warning("prowlarr.no_results", query=query, job_id=job.id)
            job.status = "failed"
            job.error_message = f"No Usenet results found for: {query}" if not tried_urls else f"All {len(tried_urls)} available NZBs already tried"
            req.status = "failed"
        else:
            # Pick the best result and submit its download URL to NZBGet
            chosen = results[0]
            log.info(
                "nzbget.submitting",
                title=chosen.title,
                indexer=chosen.indexer,
                score=chosen.score,
                job_id=job.id,
            )
            nzbid = await nzbget.append(chosen.title, chosen.download_url, settings.nzbget_category)

            job.status = "downloading"
            job.external_id = str(nzbid)
            job.source_url = chosen.download_url
            job.bytes_total = chosen.size
            req.status = "downloading"

    except Exception as e:
        log.error("nzbget.job_error", job_id=job.id, error=str(e))
        job.status = "failed"
        job.error_message = str(e)
        req.status = "failed"

    job.updated_at = datetime.now(timezone.utc)
    req.updated_at = datetime.now(timezone.utc)
    await db.commit()

    if req.status == "failed":
        await notify_request_status(db, req)


async def _run_slskd_job(db: AsyncSession, job: AcquisitionJob, req: Request) -> None:
    """Search slskd, pick best result, submit download."""
    from trackforge.adapters.acquisition.slskd import SlskdClient

    client = SlskdClient(settings.slskd_url, settings.slskd_api_key)

    if not await client.health_check():
        log.warning("slskd.unreachable", url=settings.slskd_url)
        return

    name, artist_name = await _resolve_name(db, req)
    query = _build_query(req.target_type, name, artist_name)

    job.status = "submitted"
    job.source_query = query
    job.started_at = datetime.now(timezone.utc)
    job.updated_at = datetime.now(timezone.utc)
    await db.commit()

    log.info("slskd.searching", query=query, job_id=job.id)

    try:
        search_id, candidates = await client.search(query)
        job.external_id = search_id

        if not candidates:
            job.status = "failed"
            job.error_message = f"No results found for: {query}"
            req.status = "failed"
        else:
            best = candidates[0]
            await client.download(best.username, best.files)
            job.status = "downloading"
            job.source_url = f"{best.username}/{best.directory}"
            job.bytes_total = sum(f.size for f in best.files)
            req.status = "downloading"

    except Exception as e:
        log.error("slskd.error", job_id=job.id, error=str(e))
        job.status = "failed"
        job.error_message = str(e)
        req.status = "failed"

    job.updated_at = datetime.now(timezone.utc)
    req.updated_at = datetime.now(timezone.utc)
    await db.commit()

    if req.status == "failed":
        await notify_request_status(db, req)


# ─────────────────────────────────────────────
# POLL IN-PROGRESS DOWNLOADS
# ─────────────────────────────────────────────

async def poll_downloading_jobs(db: AsyncSession) -> int:
    """Check all downloading jobs and advance state when complete."""
    result = await db.execute(select(AcquisitionJob).where(AcquisitionJob.status == "downloading"))
    jobs = result.scalars().all()
    if not jobs:
        return 0

    for job in jobs:
        if job.adapter == "nzbget":
            await _poll_nzbget_job(db, job)
        elif job.adapter == "slskd":
            await _poll_slskd_job(db, job)

    return len(jobs)


async def _poll_nzbget_job(db: AsyncSession, job: AcquisitionJob) -> None:
    from trackforge.adapters.acquisition.nzbget import NZBGetClient, DONE_STATUSES, FAILED_STATUSES

    if not job.external_id:
        return

    nzbget = NZBGetClient(settings.nzbget_url, settings.nzbget_username, settings.nzbget_password)

    try:
        nzbid = int(job.external_id)
        status = await nzbget.get_status(nzbid)
        downloaded, total = await nzbget.get_progress(nzbid)
    except Exception as e:
        log.warning("nzbget.poll_failed", job_id=job.id, error=str(e))
        return

    job.bytes_downloaded = downloaded
    if total:
        job.bytes_total = total
    job.updated_at = datetime.now(timezone.utc)

    req = await db.get(Request, job.request_id)

    # NZBGet history statuses are compound: e.g. "SUCCESS/UNPACK", "FAILURE/PAR"
    status_base = status.split("/")[0] if status else None

    if status_base in DONE_STATUSES:
        job.status = "completed"
        job.completed_at = datetime.now(timezone.utc)
        if req:
            req.status = "processing"
            req.updated_at = datetime.now(timezone.utc)
        log.info("nzbget.download_complete", job_id=job.id, status=status)

    elif status_base in FAILED_STATUSES:
        job.status = "failed"
        job.error_message = f"NZBGet status: {status}"
        job.completed_at = datetime.now(timezone.utc)
        if req:
            req.status = "failed"
            req.updated_at = datetime.now(timezone.utc)
        log.error("nzbget.download_failed", job_id=job.id, status=status)

    await db.commit()

    if req and req.status == "failed":
        await notify_request_status(db, req)


async def _poll_slskd_job(db: AsyncSession, job: AcquisitionJob) -> None:
    from trackforge.adapters.acquisition.slskd import SlskdClient

    if not job.source_url:
        return

    client = SlskdClient(settings.slskd_url, settings.slskd_api_key)
    username = job.source_url.split("/")[0]

    try:
        transfers = await client.get_user_transfers(username)
    except Exception as e:
        log.warning("slskd.poll_failed", job_id=job.id, error=str(e))
        return

    if not transfers:
        return

    total = len(transfers)
    completed = sum(1 for t in transfers if "Completed" in t.get("state", "") or t.get("percentComplete", 0) >= 100)
    failed = sum(1 for t in transfers if any(s in t.get("state", "") for s in ("Errored", "TimedOut", "Cancelled")))
    downloaded_bytes = sum(t.get("bytesTransferred", 0) for t in transfers)

    job.bytes_downloaded = downloaded_bytes
    job.updated_at = datetime.now(timezone.utc)

    req = await db.get(Request, job.request_id)

    if failed == total:
        job.status = "failed"
        job.error_message = f"All {total} transfers failed"
        job.completed_at = datetime.now(timezone.utc)
        if req:
            req.status = "failed"
            req.updated_at = datetime.now(timezone.utc)
    elif completed == total:
        job.status = "completed"
        job.completed_at = datetime.now(timezone.utc)
        if req:
            req.status = "processing"
            req.updated_at = datetime.now(timezone.utc)
        log.info("slskd.download_complete", job_id=job.id)

    await db.commit()

    if req and req.status == "failed":
        await notify_request_status(db, req)
