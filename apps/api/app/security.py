"""인증 — bcrypt 해시 + JWT 토큰."""
from __future__ import annotations
import datetime as dt
from typing import Any
import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .db import get_session
from .models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)
ALGORITHM = "HS256"
# bcrypt 는 최대 72 byte 만 사용. 사용자 입력이 그 이상이어도 안전하게 truncate.
_BCRYPT_MAX = 72


def hash_password(plain: str) -> str:
    pw = plain.encode("utf-8")[:_BCRYPT_MAX]
    return bcrypt.hashpw(pw, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    pw = plain.encode("utf-8")[:_BCRYPT_MAX]
    try:
        return bcrypt.checkpw(pw, hashed.encode("utf-8"))
    except ValueError:
        return False


def unusable_password_hash() -> str:
    """로컬 로그인이 불가능한 placeholder 해시.

    구글 전용 계정처럼 비밀번호가 없는 사용자에게 사용. 알 수 없는 무작위 입력의
    bcrypt 해시라 verify_password 가 어떤 입력에도 매칭되지 않는다
    (Django set_unusable_password 와 동일 발상).
    """
    import secrets
    return hash_password(secrets.token_urlsafe(32))


def issue_token(user: User) -> str:
    settings = get_settings()
    now = dt.datetime.now(dt.timezone.utc)
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role,
        "iat": int(now.timestamp()),
        "exp": int((now + dt.timedelta(hours=settings.jwt_expires_hours)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    except JWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"invalid token: {e}")


async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_session),
) -> User:
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing token")
    payload = decode_token(token)
    user_id = int(payload.get("sub", 0))
    user = await session.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user not found or inactive")
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin only")
    return user
