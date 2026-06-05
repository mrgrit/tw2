"""회원가입 / 로그인 / 내 정보."""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..db import get_session
from ..models import User
from ..schemas import GoogleAuthIn, LoginIn, SignupIn, TokenOut, UserOut
from ..security import get_current_user, hash_password, issue_token, verify_password
from ..services import audit, google_auth, rate_limit

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/providers")
async def providers() -> dict:
    """프론트가 어떤 소셜 로그인을 띄울지 결정하기 위한 공개 정보(인증 불필요)."""
    settings = get_settings()
    return {
        "google": {
            "enabled": bool(settings.google_client_id),
            "client_id": settings.google_client_id or None,
        }
    }


@router.post("/google", response_model=TokenOut)
async def google_login(
    body: GoogleAuthIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> TokenOut:
    rate_limit.enforce_login(request, email="google")
    try:
        claims = google_auth.verify_credential(body.credential)
    except google_auth.GoogleAuthDisabled:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "google login not configured")
    except google_auth.GoogleAuthError as e:
        await audit.record(
            session, actor=None, action="auth.google_fail",
            target_type="user", target_id=None,
            detail={"reason": str(e)}, request=request,
        )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"google login failed: {e}")

    try:
        user, created = await google_auth.resolve_user(session, claims)
    except google_auth.GoogleAuthError as e:
        await audit.record(
            session, actor=None, actor_email=claims.get("email"), action="auth.google_fail",
            target_type="user", target_id=None,
            detail={"reason": str(e)}, request=request,
        )
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(e))

    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "account disabled")

    await session.commit()
    await session.refresh(user)
    await audit.record(
        session, actor=user,
        action="auth.google_signup" if created else "auth.google",
        target_type="user", target_id=user.id,
        detail={"created": created}, request=request,
    )
    return TokenOut(access_token=issue_token(user), user=UserOut.model_validate(user))


@router.post("/signup", response_model=TokenOut)
async def signup(
    body: SignupIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> TokenOut:
    rate_limit.enforce_signup(request)
    existing = await session.scalar(select(User).where(User.email == body.email))
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "email already registered")
    user = User(
        email=str(body.email).lower(),
        name=body.name,
        password_hash=hash_password(body.password),
        role="student",
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    await audit.record(
        session, actor=user, action="auth.signup",
        target_type="user", target_id=user.id,
        detail={"name": user.name},
        request=request,
    )
    return TokenOut(access_token=issue_token(user), user=UserOut.model_validate(user))


@router.post("/login", response_model=TokenOut)
async def login(
    body: LoginIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> TokenOut:
    email = str(body.email).lower()
    rate_limit.enforce_login(request, email=email)
    user = await session.scalar(select(User).where(User.email == email))
    if not user or not verify_password(body.password, user.password_hash):
        await audit.record(
            session, actor=None, actor_email=email, action="auth.login_fail",
            target_type="user", target_id=user.id if user else None,
            detail={"reason": "invalid_credentials"},
            request=request,
        )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid email or password")
    if not user.is_active:
        await audit.record(
            session, actor=None, actor_email=email, action="auth.login_fail",
            target_type="user", target_id=user.id,
            detail={"reason": "account_disabled"},
            request=request,
        )
        raise HTTPException(status.HTTP_403_FORBIDDEN, "account disabled")
    await audit.record(
        session, actor=user, action="auth.login",
        target_type="user", target_id=user.id,
        detail={}, request=request,
    )
    return TokenOut(access_token=issue_token(user), user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)


from pydantic import BaseModel, Field


class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class UpdateProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)


@router.patch("/me", response_model=UserOut)
async def update_me(
    body: UpdateProfileIn,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> UserOut:
    prev_name = user.name
    user.name = body.name
    await session.commit()
    await session.refresh(user)
    await audit.record(
        session, actor=user, action="user.update_profile",
        target_type="user", target_id=user.id,
        detail={"prev_name": prev_name, "new_name": user.name},
        request=request,
    )
    return UserOut.model_validate(user)


@router.post("/me/password")
async def change_password(
    body: ChangePasswordIn,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if not verify_password(body.current_password, user.password_hash):
        await audit.record(
            session, actor=user, action="user.change_password_fail",
            target_type="user", target_id=user.id,
            detail={"reason": "wrong_current_password"},
            request=request,
        )
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "current password is incorrect")
    if body.new_password == body.current_password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "new password must differ from current")
    user.password_hash = hash_password(body.new_password)
    await session.commit()
    await audit.record(
        session, actor=user, action="user.change_password",
        target_type="user", target_id=user.id,
        detail={}, request=request,
    )
    return {"ok": True}
