"""
User management endpoints (admin only).

Provides CRUD operations for managing users in the system.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from trackforge.api.deps import get_db, require_admin
from trackforge.auth import hash_password
from trackforge.db.models import User

router = APIRouter(prefix="/users", tags=["users"])


# ─────────────────────────────────────────────
# SCHEMAS
# ─────────────────────────────────────────────

class UserListItem(BaseModel):
    id: str
    username: str
    email: str | None
    role: str
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None

    model_config = {"from_attributes": True}


class CreateUserRequest(BaseModel):
    username: str
    password: str
    email: str | None = None
    role: str = "user"

    @field_validator("username")
    @classmethod
    def username_valid(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3:
            raise ValueError("Username must be at least 3 characters")
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError("Username may only contain letters, numbers, hyphens, underscores")
        return v

    @field_validator("password")
    @classmethod
    def password_valid(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v

    @field_validator("role")
    @classmethod
    def role_valid(cls, v: str) -> str:
        if v not in ("admin", "moderator", "user"):
            raise ValueError("Role must be admin, moderator, or user")
        return v


class UpdateUserRequest(BaseModel):
    role: str | None = None
    is_active: bool | None = None
    password: str | None = None

    @field_validator("role")
    @classmethod
    def role_valid(cls, v: str | None) -> str | None:
        if v is not None and v not in ("admin", "moderator", "user"):
            raise ValueError("Role must be admin, moderator, or user")
        return v

    @field_validator("password")
    @classmethod
    def password_valid(cls, v: str | None) -> str | None:
        if v is not None and len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


# ─────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────

@router.get("", response_model=list[UserListItem])
async def list_users(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    result = await db.execute(select(User).order_by(User.created_at))
    return result.scalars().all()


@router.post("", response_model=UserListItem, status_code=201)
async def create_user(
    body: CreateUserRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    existing = await db.execute(select(User).where(User.username == body.username))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username already taken")

    user = User(
        id=str(uuid.uuid4()),
        username=body.username,
        email=body.email,
        password_hash=hash_password(body.password),
        role=body.role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserListItem)
async def update_user(
    user_id: str,
    body: UpdateUserRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Prevent admins from locking themselves out
    if user.id == admin.id:
        if body.role is not None and body.role != admin.role:
            raise HTTPException(status_code=400, detail="Cannot change your own role")
        if body.is_active is False:
            raise HTTPException(status_code=400, detail="Cannot deactivate your own account")

    if body.role is not None:
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active
    if body.password is not None:
        user.password_hash = hash_password(body.password)

    await db.commit()
    await db.refresh(user)
    return user
