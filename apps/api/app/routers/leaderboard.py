"""Phase 6 — 리더보드.

  GET /leaderboard/users        — 사용자 누적 (총점 / battle 수 / 승수 / 평균)
  GET /leaderboard/battles/{id} — 단일 battle 의 참가자 ranking + 미션별 evidence
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Battle, BattleEvent, BattleParticipant, Scenario, User
from ..security import get_current_user

router = APIRouter(prefix="/leaderboard", tags=["leaderboard"])


class UserRankRow(BaseModel):
    user_id: int
    name: str
    email: str
    role: str
    battle_count: int
    total_score: int
    win_count: int
    avg_score: float


class BattleRankRow(BaseModel):
    user_id: int
    name: str
    role_in_battle: str
    score: int
    rank: int
    events_red: int
    events_blue: int


class BattleLeaderboard(BaseModel):
    battle_id: int
    scenario_title: str | None
    mode: str
    status: str
    rows: list[BattleRankRow]


@router.get("/users", response_model=list[UserRankRow])
async def user_leaderboard(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[UserRankRow]:
    # 사용자별 합산 — completed 만 win_count 에 반영
    stmt = (
        select(
            User.id, User.name, User.email, User.role,
            func.count(BattleParticipant.id).label("battle_count"),
            func.coalesce(func.sum(BattleParticipant.score), 0).label("total_score"),
        )
        .join(BattleParticipant, BattleParticipant.user_id == User.id, isouter=True)
        .group_by(User.id, User.name, User.email, User.role)
        .order_by(func.coalesce(func.sum(BattleParticipant.score), 0).desc())
        .limit(50)
    )
    rows = (await session.execute(stmt)).all()

    # win_count: 그 battle 에서 가장 높은 점수를 받은 participant 의 user_id
    wins: dict[int, int] = {}
    battles = (await session.scalars(select(Battle).where(Battle.status == "completed"))).all()
    for b in battles:
        parts = (await session.scalars(
            select(BattleParticipant).where(BattleParticipant.battle_id == b.id)
        )).all()
        if not parts:
            continue
        top = max(parts, key=lambda p: p.score)
        # 동점은 무시 (모두 win 으로 세지 않음)
        ties = [p for p in parts if p.score == top.score]
        if len(ties) == 1 and top.score > 0:
            wins[top.user_id] = wins.get(top.user_id, 0) + 1

    out: list[UserRankRow] = []
    for r in rows:
        bc = int(r.battle_count or 0)
        ts = int(r.total_score or 0)
        out.append(UserRankRow(
            user_id=r.id, name=r.name, email=r.email, role=r.role,
            battle_count=bc, total_score=ts,
            win_count=int(wins.get(r.id, 0)),
            avg_score=round(ts / bc, 2) if bc else 0.0,
        ))
    return out


@router.get("/battles/{battle_id}", response_model=BattleLeaderboard)
async def battle_leaderboard(
    battle_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> BattleLeaderboard:
    b = await session.get(Battle, battle_id)
    if not b:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "battle not found")

    participants = (await session.scalars(
        select(BattleParticipant).where(BattleParticipant.battle_id == battle_id)
    )).all()
    by_user_id = {p.user_id: p for p in participants}

    events = (await session.scalars(
        select(BattleEvent).where(BattleEvent.battle_id == battle_id)
    )).all()

    red_user_ids = {p.user_id for p in participants if p.role in ("red", "solo")}
    blue_user_ids = {p.user_id for p in participants if p.role in ("blue", "solo")}

    red_evs: dict[int, int] = {}
    blue_evs: dict[int, int] = {}
    for e in events:
        if e.actor_user_id is None:
            continue
        if e.event_type in ("attack", "exploit") and e.actor_user_id in red_user_ids:
            red_evs[e.actor_user_id] = red_evs.get(e.actor_user_id, 0) + 1
        elif e.event_type in ("defend", "detect", "block") and e.actor_user_id in blue_user_ids:
            blue_evs[e.actor_user_id] = blue_evs.get(e.actor_user_id, 0) + 1

    user_ids = list(by_user_id.keys())
    users = {
        u.id: u for u in (await session.scalars(
            select(User).where(User.id.in_(user_ids))
        )).all()
    }

    sorted_parts = sorted(participants, key=lambda p: p.score, reverse=True)
    rows: list[BattleRankRow] = []
    for idx, p in enumerate(sorted_parts, start=1):
        u = users.get(p.user_id)
        rows.append(BattleRankRow(
            user_id=p.user_id,
            name=u.name if u else f"user-{p.user_id}",
            role_in_battle=p.role,
            score=p.score,
            rank=idx,
            events_red=red_evs.get(p.user_id, 0),
            events_blue=blue_evs.get(p.user_id, 0),
        ))

    title = None
    if b.scenario_id:
        s = await session.get(Scenario, b.scenario_id)
        title = s.title if s else None

    return BattleLeaderboard(
        battle_id=b.id, scenario_title=title, mode=b.mode, status=b.status, rows=rows,
    )
