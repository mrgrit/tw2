"""구글 로그인 — GIS ID 토큰 검증 + 사용자 매핑.

프론트(Google Identity Services)가 받은 ID 토큰(credential)을 백엔드가 검증해
서명/aud(client_id)/iss/exp 를 확인하고, claims → tubewar User 로 매핑한다.
정책: 첫 로그인 시 학생 자동 가입(GOOGLE_AUTO_PROVISION), 도메인 제한 선택(GOOGLE_ALLOWED_DOMAIN).

검증 본체(_verify)는 google-auth 로 네트워크(구글 인증서)에 의존하므로 테스트에서
monkeypatch 한다.
"""
from __future__ import annotations
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..models import User
from ..security import unusable_password_hash

log = logging.getLogger(__name__)

_GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}


class GoogleAuthError(Exception):
    """검증 실패 / 정책 위반(401)."""


class GoogleAuthDisabled(GoogleAuthError):
    """GOOGLE_CLIENT_ID 미설정(503)."""


def enabled() -> bool:
    return bool(get_settings().google_client_id)


def _verify(credential: str, client_id: str) -> dict:
    """실제 구글 ID 토큰 검증. (테스트에서 monkeypatch 대상)"""
    from google.auth.transport import requests as g_requests
    from google.oauth2 import id_token

    return id_token.verify_oauth2_token(credential, g_requests.Request(), client_id)


def verify_credential(credential: str) -> dict:
    """credential(ID 토큰) → 검증된 claims. 실패 시 GoogleAuthError."""
    settings = get_settings()
    if not settings.google_client_id:
        raise GoogleAuthDisabled("google login not configured")
    try:
        claims = _verify(credential, settings.google_client_id)
    except GoogleAuthError:
        raise
    except Exception as e:  # 서명/만료/aud 불일치 등
        raise GoogleAuthError(f"invalid google token: {e}") from e

    if claims.get("iss") not in _GOOGLE_ISSUERS:
        raise GoogleAuthError("bad token issuer")
    email = (claims.get("email") or "").lower()
    if not email:
        raise GoogleAuthError("token has no email")
    if claims.get("email_verified") is False:
        raise GoogleAuthError("google email not verified")

    allowed = settings.google_allowed_domain.strip().lower()
    if allowed:
        domain = (claims.get("hd") or email.rsplit("@", 1)[-1]).lower()
        if domain != allowed:
            raise GoogleAuthError(f"domain not allowed: {domain}")
    return claims


async def resolve_user(session: AsyncSession, claims: dict) -> tuple[User, bool]:
    """검증된 claims → User. (user, created) 반환. 미가입+자동가입off 면 GoogleAuthError."""
    settings = get_settings()
    sub = str(claims.get("sub") or "")
    email = (claims.get("email") or "").lower()
    name = claims.get("name") or email.rsplit("@", 1)[0]
    if not sub:
        raise GoogleAuthError("token has no subject")

    # 1) 이미 구글로 연결된 계정
    user = await session.scalar(select(User).where(User.google_sub == sub))
    if user is not None:
        return user, False

    # 2) 같은 이메일의 기존(로컬) 계정 → 구글 연결만 추가(로컬 로그인은 그대로 유지)
    user = await session.scalar(select(User).where(User.email == email))
    if user is not None:
        user.google_sub = sub
        log.info("google linked to existing account: %s", email)
        return user, False

    # 3) 신규 — 자동 가입 정책
    if not settings.google_auto_provision:
        raise GoogleAuthError("account not registered (auto-provision disabled)")
    user = User(
        email=email,
        name=name,
        role="student",
        is_active=True,
        auth_provider="google",
        google_sub=sub,
        password_hash=unusable_password_hash(),
    )
    session.add(user)
    log.info("google auto-provisioned new student: %s", email)
    return user, True
