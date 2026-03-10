"""
Admin settings endpoints.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from trackforge.api.deps import get_current_user, require_admin
from trackforge.database import get_db
from trackforge.db.models import User
from trackforge.domain.services.settings_service import get_all_settings, update_settings

router = APIRouter(prefix="/settings", tags=["settings"])


class SettingsResponse(BaseModel):
    registration_enabled: bool
    require_approval: bool
    library_folder_pattern: str
    file_naming_pattern: str


class SettingsUpdateRequest(BaseModel):
    registration_enabled: bool | None = None
    require_approval: bool | None = None
    library_folder_pattern: str | None = None
    file_naming_pattern: str | None = None


def _to_response(raw: dict[str, str]) -> SettingsResponse:
    return SettingsResponse(
        registration_enabled=raw.get("registration_enabled", "true").lower() in ("true", "1", "yes"),
        require_approval=raw.get("require_approval", "true").lower() in ("true", "1", "yes"),
        library_folder_pattern=raw.get("library_folder_pattern", "{artist}/{album} [{year}]"),
        file_naming_pattern=raw.get("file_naming_pattern", "{track}-{artist}-{title}"),
    )


@router.get("", response_model=SettingsResponse)
async def get_settings(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Any authenticated user can read settings (needed for login page registration check)."""
    raw = await get_all_settings(db)
    return _to_response(raw)


@router.patch("", response_model=SettingsResponse)
async def patch_settings(
    body: SettingsUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    updates: dict[str, str] = {}
    if body.registration_enabled is not None:
        updates["registration_enabled"] = str(body.registration_enabled).lower()
    if body.require_approval is not None:
        updates["require_approval"] = str(body.require_approval).lower()
    if body.library_folder_pattern is not None:
        updates["library_folder_pattern"] = body.library_folder_pattern
    if body.file_naming_pattern is not None:
        updates["file_naming_pattern"] = body.file_naming_pattern

    if updates:
        raw = await update_settings(db, updates)
    else:
        raw = await get_all_settings(db)

    return _to_response(raw)
