"""회원가입 / 로그인 / 내 정보."""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import User
from ..schemas import LoginIn, SignupIn, TokenOut, UserOut
from ..security import get_current_user, hash_password, issue_token, verify_password
from ..services import audit, rate_limit

router = APIRouter(prefix="/auth", tags=["auth"])


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
