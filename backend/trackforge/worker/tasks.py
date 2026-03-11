"""
ARQ worker task functions.

Each function is an ARQ job or cron target. They receive a context dict
with a shared DB session factory injected at worker startup.
"""

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from trackforge.domain.services.acquisition_service import (
    dispatch_approved_requests,
    poll_downloading_jobs,
    run_queued_jobs,
)
from trackforge.domain.services.processing_service import process_processing_requests
from trackforge.domain.services.review_service import auto_import_pending_reviews

log = structlog.get_logger()


async def process_acquisition_pipeline(ctx: dict) -> dict:
    """
    Full acquisition pipeline in one cron pass:
    1. Dispatch newly approved requests → create queued jobs
    2. Run queued jobs → search slskd + submit downloads
    3. Poll downloading jobs → detect completion

    Runs every minute via cron.
    """
    async_session_factory = ctx["db_factory"]

    async with async_session_factory() as db:
        dispatched = await dispatch_approved_requests(db)

    async with async_session_factory() as db:
        searched = await run_queued_jobs(db)

    async with async_session_factory() as db:
        polled = await poll_downloading_jobs(db)

    async with async_session_factory() as db:
        moved = await process_processing_requests(db)

    async with async_session_factory() as db:
        auto_imported = await auto_import_pending_reviews(db)

    result = {"dispatched": dispatched, "searched": searched, "polled": polled, "moved": moved, "auto_imported": auto_imported}
    if any(result.values()):
        log.info("acquisition.pipeline", **result)
    return result


async def sync_jellyfin_library(ctx: dict) -> dict:
    """
    Sync the Jellyfin music library into the library_items table.
    Checks the configured scan interval before running.
    """
    from trackforge.domain.services.jellyfin_sync_service import (
        auto_resolve_requests,
        sync_jellyfin_library as do_sync,
    )
    from trackforge.domain.services.settings_service import get_setting

    async_session_factory = ctx["db_factory"]

    # Check if enough time has elapsed since the last sync
    last_sync = ctx.get("last_jellyfin_sync")
    async with async_session_factory() as db:
        interval_str = await get_setting(db, "jellyfin_scan_interval")

    interval_minutes = max(5, int(interval_str or "30"))

    import time
    now = time.time()
    if last_sync and (now - last_sync) < interval_minutes * 60:
        return {"skipped": True}

    async with async_session_factory() as db:
        synced = await do_sync(db)

    resolved = 0
    if synced:
        async with async_session_factory() as db:
            resolved = await auto_resolve_requests(db)
        log.info("jellyfin_sync.cron", synced=synced, resolved=resolved)

    ctx["last_jellyfin_sync"] = now
    return {"synced": synced, "resolved": resolved}
