"""
App settings service — DB-backed with Redis cache.

Settings are key-value pairs stored in the app_settings table.
Reads are cached in Redis for 5 minutes to avoid hitting the DB on every request.
"""

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from trackforge.cache import cache_delete, cache_get, cache_set
from trackforge.db.models import AppSetting

log = logging.getLogger(__name__)

CACHE_KEY = "app:settings"
CACHE_TTL = 60 * 5  # 5 minutes

# Default values — used when a key doesn't exist in DB
DEFAULTS: dict[str, str] = {
    "registration_enabled": "true",
    "require_approval": "true",
    "library_folder_pattern": "{artist}/{album} [{year}]",
    "file_naming_pattern": "{track}-{artist}-{title}",
}


async def get_all_settings(db: AsyncSession) -> dict[str, str]:
    """Return all settings as a dict, with defaults for missing keys."""
    cached = await cache_get(CACHE_KEY)
    if cached is not None:
        return cached

    try:
        result = await db.execute(select(AppSetting))
        rows = result.scalars().all()
    except Exception:
        log.warning("app_settings table not available, using defaults")
        await db.rollback()
        return {**DEFAULTS}

    settings = {**DEFAULTS}
    for row in rows:
        settings[row.key] = row.value

    await cache_set(CACHE_KEY, settings, ttl=CACHE_TTL)
    return settings


async def get_setting(db: AsyncSession, key: str) -> str:
    """Get a single setting value."""
    all_settings = await get_all_settings(db)
    return all_settings.get(key, DEFAULTS.get(key, ""))


async def get_setting_bool(db: AsyncSession, key: str) -> bool:
    """Get a setting as a boolean."""
    val = await get_setting(db, key)
    return val.lower() in ("true", "1", "yes")


async def update_settings(db: AsyncSession, updates: dict[str, str]) -> dict[str, str]:
    """Update one or more settings. Returns the full settings dict after update."""
    now = datetime.now(timezone.utc)
    for key, value in updates.items():
        existing = await db.get(AppSetting, key)
        if existing:
            existing.value = value
            existing.updated_at = now
        else:
            db.add(AppSetting(key=key, value=value, updated_at=now))

    await db.commit()
    await cache_delete(CACHE_KEY)
    return await get_all_settings(db)
