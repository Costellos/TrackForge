"""
Auth endpoints — register, login, me.

First user to register is automatically granted admin role.
Subsequent users get the 'user' role by default.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from trackforge.api.deps import get_current_user
from trackforge.auth import create_access_token, hash_password, verify_password
from trackforge.database import get_db
from trackforge.db.models import User
from trackforge.domain.services.settings_service import get_setting_bool

router = APIRouter(prefix="/auth", tags=["auth"])


# ─────────────────────────────────────────────
# SCHEMAS
# ─────────────────────────────────────────────

class RegisterRequest(BaseModel):
    username: str
    password: str
    email: str | None = None

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


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: str
    username: str
    email: str | None
    role: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────

@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    # First user always allowed (bootstraps the admin account)
    count = await db.execute(select(func.count()).select_from(User))
    is_first = count.scalar() == 0

    if not is_first:
        reg_enabled = await get_setting_bool(db, "registration_enabled")
        if not reg_enabled:
            raise HTTPException(status_code=403, detail="Registration is disabled")

    # Check username taken
    existing = await db.execute(select(User).where(User.username == body.username))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username already taken")

    user = User(
        id=str(uuid.uuid4()),
        username=body.username,
        email=body.email,
        password_hash=hash_password(body.password),
        role="admin" if is_first else "user",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    token = create_access_token({"sub": user.id, "role": user.role})
    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == body.username))
    user = result.scalar_one_or_none()

    if not user or not user.password_hash or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")

    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()

    token = create_access_token({"sub": user.id, "role": user.role})
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)):
    return user


class RegistrationStatusResponse(BaseModel):
    registration_enabled: bool


@router.get("/registration-status", response_model=RegistrationStatusResponse)
async def registration_status(db: AsyncSession = Depends(get_db)):
    """Public endpoint — login page checks this to show/hide the register tab."""
    enabled = await get_setting_bool(db, "registration_enabled")
    return RegistrationStatusResponse(registration_enabled=enabled)
