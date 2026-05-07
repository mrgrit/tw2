"""공방전 라우터 — Phase 2: solo / duel / ffa, 이벤트 push, SSE 스트림.

Phase 4 (Claude Code monitor) 에서는 별도 background task 가 자동으로
add_event 를 호출. 본 라우터는 manual + 자동 두 경로 모두 통과.
"""
from __future__ import annotations
import asyncio
import json
from typing import AsyncIterator
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..db import SessionLocal, get_session
from ..models import Battle, BattleEvent, BattleParticipant, Scenario, User
from ..schemas import (
    BattleCreateIn, BattleDetail, BattleEventIn, BattleEventOut,
    BattleOut, BattleParticipantOut,
)
from ..security import get_current_user, require_admin
from ..services import auto_monitor, battle_service as bs

router = APIRouter(prefix="/battles", tags=["battles"])


def _serialize(b: Battle, scenario_title: str | None) -> BattleDetail:
    elapsed, remaining = bs.battle_elapsed(b)
    return BattleDetail(
        battle=BattleOut.model_validate(b),
        scenario_title=scenario_title,
        participants=[BattleParticipantOut.model_validate(p) for p in b.participants],
        events=[BattleEventOut.model_validate(e) for e in b.events],
        elapsed_sec=round(elapsed, 1),
        remaining_sec=round(remaining, 1),
    )


# ── List / detail ───────────────────────────────────
@router.get("", response_model=list[BattleOut])
async def list_battles(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[BattleOut]:
    rows = (await session.scalars(
        select(Battle).order_by(Battle.id.desc()).limit(100)
    )).all()
    return [BattleOut.model_validate(r) for r in rows]


@router.get("/{battle_id}", response_model=BattleDetail)
async def get_battle(
    battle_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> BattleDetail:
    try:
        b = await bs.load_battle(session, battle_id)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "battle not found")
    title = None
    if b.scenario_id:
        s = await session.get(Scenario, b.scenario_id)
        title = s.title if s else None
    return _serialize(b, title)


# ── Create / start / end ────────────────────────────
@router.post("", response_model=BattleDetail, status_code=201)
async def create_battle(
    body: BattleCreateIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> BattleDetail:
    parts = [p.model_dump() for p in body.participants]
    # solo 모드는 본인만 참가 강제 (관리자 제외)
    if body.mode == "solo" and user.role != "admin":
        if parts[0]["user_id"] != user.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "solo battle must include yourself only")
    # duel/ffa: 비-admin 은 자기 자신을 포함해야
    if body.mode in ("duel", "ffa") and user.role != "admin":
        if user.id not in {p["user_id"] for p in parts}:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "you must include yourself as a participant")

    try:
        b = await bs.create_battle(
            session,
            scenario_id=body.scenario_id,
            mode=body.mode,
            monitor=body.monitor,
            participants=parts,
            created_by=user.id,
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))

    s = await session.get(Scenario, b.scenario_id) if b.scenario_id else None
    return _serialize(b, s.title if s else None)


@router.post("/{battle_id}/start", response_model=BattleDetail)
async def start_battle(
    battle_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> BattleDetail:
    if user.role != "admin" and not await bs.is_participant(session, battle_id, user.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only participants or admin can start")
    try:
        b = await bs.start_battle(session, battle_id, actor_user_id=user.id)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    # Phase 4 — auto-monitor 활성화
    if b.monitor == "bastion":
        auto_monitor.start(battle_id)
    s = await session.get(Scenario, b.scenario_id) if b.scenario_id else None
    return _serialize(b, s.title if s else None)


@router.post("/{battle_id}/events", response_model=BattleEventOut, status_code=201)
async def post_event(
    battle_id: int,
    body: BattleEventIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> BattleEventOut:
    if user.role != "admin" and not await bs.is_participant(session, battle_id, user.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only participants or admin can post events")
    try:
        ev = await bs.add_event(
            session,
            battle_id=battle_id,
            actor_user_id=user.id,
            event_type=body.event_type,
            target=body.target,
            description=body.description,
            points=body.points,
            detail=body.detail,
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    return BattleEventOut.model_validate(ev)


@router.post("/{battle_id}/end", response_model=BattleDetail)
async def end_battle(
    battle_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> BattleDetail:
    if user.role != "admin" and not await bs.is_participant(session, battle_id, user.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only participants or admin can end")
    try:
        b = await bs.end_battle(session, battle_id, actor_user_id=user.id)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    auto_monitor.stop(battle_id)
    s = await session.get(Scenario, b.scenario_id) if b.scenario_id else None
    return _serialize(b, s.title if s else None)


@router.delete("/{battle_id}", status_code=204)
async def delete_battle(
    battle_id: int,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> None:
    b = await session.get(Battle, battle_id)
    if not b:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "battle not found")
    await session.delete(b)
    await session.commit()


@router.post("/{battle_id}/cancel", response_model=BattleDetail)
async def cancel_battle(
    battle_id: int,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> BattleDetail:
    try:
        b = await bs.cancel_battle(session, battle_id, actor_user_id=admin.id)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    auto_monitor.stop(battle_id)
    s = await session.get(Scenario, b.scenario_id) if b.scenario_id else None
    return _serialize(b, s.title if s else None)


# ── SSE 라이브 스트림 ───────────────────────────────
@router.get("/{battle_id}/stream")
async def stream_events(
    battle_id: int,
    request: Request,
    poll_interval: float = 1.0,
    user: User = Depends(get_current_user),
):
    """text/event-stream — 새 이벤트 + 점수판 push.

    구현 단순화 — DB 폴링 (poll_interval 초). Phase 6 에서 redis pubsub 등으로 대체.
    """
    # 권한 — 참가자 또는 admin (관전자 역할 추가는 Phase 7)
    async with SessionLocal() as s0:
        if user.role != "admin" and not await bs.is_participant(s0, battle_id, user.id):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "not a participant")

    async def gen() -> AsyncIterator[bytes]:
        last_event_id = 0
        # snapshot 1회
        async with SessionLocal() as s:
            b = await bs.load_battle(s, battle_id)
            scoreboard = {p.role: {"user_id": p.user_id, "score": p.score} for p in b.participants}
            yield _sse("snapshot", {
                "battle_id": b.id, "status": b.status, "mode": b.mode,
                "scoreboard": scoreboard,
                "elapsed": bs.battle_elapsed(b)[0],
                "remaining": bs.battle_elapsed(b)[1],
            })
            for e in b.events:
                last_event_id = max(last_event_id, e.id)
                yield _sse("event", _event_payload(e))

        # 폴링 루프
        while True:
            if await request.is_disconnected():
                return
            await asyncio.sleep(poll_interval)
            async with SessionLocal() as s:
                rows = (await s.scalars(
                    select(BattleEvent)
                    .where(BattleEvent.battle_id == battle_id, BattleEvent.id > last_event_id)
                    .order_by(BattleEvent.id.asc())
                )).all()
                for e in rows:
                    last_event_id = e.id
                    yield _sse("event", _event_payload(e))
                # 매 사이클 점수판 갱신
                parts = (await s.scalars(
                    select(BattleParticipant).where(BattleParticipant.battle_id == battle_id)
                )).all()
                b2 = await s.get(Battle, battle_id)
                if b2 is None:
                    yield _sse("end", {"reason": "deleted"})
                    return
                yield _sse("scoreboard", {
                    "status": b2.status,
                    "scoreboard": {p.role: {"user_id": p.user_id, "score": p.score} for p in parts},
                    "elapsed": bs.battle_elapsed(b2)[0],
                    "remaining": bs.battle_elapsed(b2)[1],
                })
                if b2.status in ("completed", "cancelled"):
                    yield _sse("end", {"reason": b2.status})
                    return

    return StreamingResponse(gen(), media_type="text/event-stream")


def _sse(event: str, data: dict) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n".encode("utf-8")


def _event_payload(e: BattleEvent) -> dict:
    return {
        "id": e.id, "ts": e.ts.isoformat() if e.ts else None,
        "actor_user_id": e.actor_user_id,
        "event_type": e.event_type,
        "target": e.target, "description": e.description,
        "detail": e.detail or {},
        "points": e.points,
    }
