"""공방전 라우터 — Phase 1 placeholder. 실제 로직은 Phase 2 에서.

엔드포인트만 노출하고 본문은 stub. 응답 스키마는 확정.
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Battle, User
from ..schemas import BattleOut
from ..security import get_current_user

router = APIRouter(prefix="/battles", tags=["battles"])


@router.get("", response_model=list[BattleOut])
async def list_battles(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)) -> list[BattleOut]:
    rows = (await session.scalars(select(Battle).order_by(Battle.id.desc()).limit(50))).all()
    return [BattleOut.model_validate(r) for r in rows]


@router.get("/{battle_id}", response_model=BattleOut)
async def get_battle(battle_id: int, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)) -> BattleOut:
    b = await session.get(Battle, battle_id)
    if not b:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "battle not found")
    return BattleOut.model_validate(b)
