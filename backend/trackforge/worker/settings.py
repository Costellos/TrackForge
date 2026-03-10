from arq import cron
from arq.connections import RedisSettings

from trackforge.config import get_settings
from trackforge.database import AsyncSessionLocal
from trackforge.worker.tasks import process_acquisition_pipeline, sync_jellyfin_library

settings = get_settings()


def _redis_settings() -> RedisSettings:
    url = settings.redis_url  # e.g. redis://redis:6379/0
    # arq RedisSettings wants host/port/db separately
    from urllib.parse import urlparse
    parsed = urlparse(url)
    return RedisSettings(
        host=parsed.hostname or "redis",
        port=parsed.port or 6379,
        database=int(parsed.path.lstrip("/") or 0),
    )


async def startup(ctx: dict) -> None:
    ctx["db_factory"] = AsyncSessionLocal


async def shutdown(ctx: dict) -> None:
    pass


class WorkerSettings:
    redis_settings = _redis_settings()
    on_startup = startup
    on_shutdown = shutdown
    functions = [process_acquisition_pipeline, sync_jellyfin_library]
    cron_jobs = [
        cron(process_acquisition_pipeline, minute=set(range(60)), second=0, run_at_startup=True),
        # Sync Jellyfin library every 30 minutes
        cron(sync_jellyfin_library, minute={0, 30}, second=10, run_at_startup=True),
    ]
