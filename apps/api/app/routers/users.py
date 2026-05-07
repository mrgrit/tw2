"""학생용 user 조회 — duel/ffa 참가자 초대용 lookup."""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import User
from ..security import get_current_user

router = APIRouter(prefix="/users", tags=["users"])


class UserLookupOut(BaseModel):
    id: int
    email: str
    name: str
    role: str


@router.get("/lookup", response_model=UserLookupOut)
async def lookup(
    email: str,
    me: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> UserLookupOut:
    """이메일로 활성 사용자 1명 찾기. duel/ffa 초대 UX 용."""
    e = email.strip().lower()
    if "@" not in e or len(e) > 255:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid email")
    u = await session.scalar(select(User).where(User.email == e))
    if not u or not u.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    return UserLookupOut(id=u.id, email=u.email, name=u.name, role=u.role)
