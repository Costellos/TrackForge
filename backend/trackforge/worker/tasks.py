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

    result = {"dispatched": dispatched, "searched": searched, "polled": polled, "moved": moved}
    if any(result.values()):
        log.info("acquisition.pipeline", **result)
    return result


async def sync_jellyfin_library(ctx: dict) -> dict:
    """
    Sync the Jellyfin music library into the library_items table.
    Runs every 30 minutes via cron.
    """
    from trackforge.domain.services.jellyfin_sync_service import sync_jellyfin_library as do_sync

    async_session_factory = ctx["db_factory"]

    async with async_session_factory() as db:
        synced = await do_sync(db)

    if synced:
        log.info("jellyfin_sync.cron", synced=synced)
    return {"synced": synced}
