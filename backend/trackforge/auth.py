"""
Auth utilities — password hashing, JWT creation and verification.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from jose import jwt

from trackforge.config import get_settings

settings = get_settings()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(data: dict[str, Any]) -> str:
    payload = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload["exp"] = expire
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def decode_token(token: str) -> dict[str, Any]:
    """Raises JWTError if token is invalid or expired."""
    return jwt.decode(token, settings.secret_key, algorithms=["HS256"])
