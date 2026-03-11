"""
Discord webhook adapter.
Sends rich embed notifications to a Discord channel via webhook URL.
"""

from typing import Any

import httpx
import structlog

log = structlog.get_logger()

# Status → embed color mapping
STATUS_COLORS = {
    "pending_approval": 0xFBBF24,  # amber
    "approved": 0x3B82F6,          # blue
    "rejected": 0xF97316,          # orange
    "searching": 0xA855F7,         # purple
    "downloading": 0x38BDF8,       # sky
    "processing": 0x8B5CF6,        # violet
    "pending_review": 0xC084FC,    # lavender
    "available": 0x4ADE80,         # green
    "failed": 0xEF4444,            # red
    "cancelled": 0x737373,         # gray
}

STATUS_LABELS = {
    "pending_approval": "New Request (Pending Approval)",
    "approved": "Request Approved",
    "rejected": "Request Rejected",
    "searching": "Searching",
    "downloading": "Downloading",
    "processing": "Processing",
    "pending_review": "Pending Tag Review",
    "available": "Now Available",
    "failed": "Request Failed",
    "cancelled": "Request Cancelled",
}


async def send_webhook(
    webhook_url: str,
    *,
    status: str,
    name: str,
    artist_name: str | None = None,
    target_type: str = "collection",
    requested_by: str | None = None,
    cover_art_url: str | None = None,
    extra_fields: list[dict[str, Any]] | None = None,
) -> None:
    """
    Send a Discord webhook embed for a request status change.
    Fire-and-forget — errors are logged but never raised.
    """
    if not webhook_url:
        return

    color = STATUS_COLORS.get(status, 0x555555)
    title = STATUS_LABELS.get(status, status.replace("_", " ").title())

    type_label = {"artist": "Artist", "collection": "Album", "song": "Song"}.get(
        target_type, target_type.title()
    )

    description = f"**{name}**"
    if artist_name:
        description += f"\nby {artist_name}"

    fields = [{"name": "Type", "value": type_label, "inline": True}]
    if requested_by:
        fields.append({"name": "Requested by", "value": requested_by, "inline": True})
    if extra_fields:
        fields.extend(extra_fields)

    embed: dict[str, Any] = {
        "title": title,
        "description": description,
        "color": color,
        "fields": fields,
    }

    if cover_art_url:
        embed["thumbnail"] = {"url": cover_art_url}

    payload = {
        "username": "TrackForge",
        "embeds": [embed],
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(webhook_url, json=payload)
            if resp.status_code >= 400:
                log.warning(
                    "discord.webhook_error",
                    status_code=resp.status_code,
                    body=resp.text[:200],
                )
    except Exception as e:
        log.warning("discord.webhook_failed", error=str(e))
