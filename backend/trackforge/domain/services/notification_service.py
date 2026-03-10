"""
Notification service.

Sends Discord webhook notifications on request status changes.
All calls are fire-and-forget — failures are logged but never block the caller.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import structlog

from trackforge.adapters.notifications.discord import send_webhook
from trackforge.config import get_settings
from trackforge.db.models import (
    Artist,
    ArtistCredit,
    Collection,
    ExternalIdentifier,
    Request,
    Song,
    User,
)

log = structlog.get_logger()

# Statuses that trigger a notification
NOTIFY_STATUSES = {
    "pending_approval",
    "approved",
    "rejected",
    "available",
    "failed",
}


async def _resolve_request_details(
    db: AsyncSession, request: Request
) -> tuple[str, str | None, str | None]:
    """
    Resolve (name, artist_name, cover_art_url) for a request.
    """
    name = request.target_id
    artist_name = None
    mbid = None

    if request.target_type == "artist":
        artist = await db.get(Artist, request.target_id)
        if artist:
            name = artist.name

    elif request.target_type == "collection":
        col = await db.get(Collection, request.target_id)
        if col:
            name = col.title
            if col.primary_artist_id:
                artist = await db.get(Artist, col.primary_artist_id)
                if artist:
                    artist_name = artist.name
            # Get MBID for cover art
            ext = await db.execute(
                select(ExternalIdentifier).where(
                    ExternalIdentifier.entity_type == "collection",
                    ExternalIdentifier.entity_id == col.id,
                    ExternalIdentifier.provider == "musicbrainz",
                )
            )
            ext_id = ext.scalar_one_or_none()
            if ext_id:
                mbid = ext_id.external_id

    elif request.target_type == "song":
        song = await db.get(Song, request.target_id)
        if song:
            name = song.title
            credit_result = await db.execute(
                select(ArtistCredit).where(
                    ArtistCredit.song_id == song.id,
                    ArtistCredit.role == "primary",
                ).order_by(ArtistCredit.position)
            )
            credit = credit_result.scalar_one_or_none()
            if credit:
                artist = await db.get(Artist, credit.artist_id)
                if artist:
                    artist_name = artist.name

    cover_art_url = None
    if mbid:
        cover_art_url = f"https://coverartarchive.org/release-group/{mbid}/front-250"

    return name, artist_name, cover_art_url


async def notify_request_status(
    db: AsyncSession,
    request: Request,
    *,
    status_override: str | None = None,
) -> None:
    """
    Send a Discord notification for a request status change.
    Only notifies for statuses in NOTIFY_STATUSES.
    """
    settings = get_settings()
    if not settings.discord_webhook_url:
        return

    status = status_override or request.status
    if status not in NOTIFY_STATUSES:
        return

    try:
        name, artist_name, cover_art_url = await _resolve_request_details(db, request)

        # Resolve requester username
        requested_by = None
        if request.user_id:
            user = await db.get(User, request.user_id)
            if user:
                requested_by = user.username

        await send_webhook(
            settings.discord_webhook_url,
            status=status,
            name=name,
            artist_name=artist_name,
            target_type=request.target_type,
            requested_by=requested_by,
            cover_art_url=cover_art_url,
        )
    except Exception as e:
        log.warning("notification.failed", error=str(e), request_id=request.id)
