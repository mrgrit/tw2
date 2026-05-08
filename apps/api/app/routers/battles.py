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
from ..services import auto_monitor, battle_service as bs, hints as hint_svc

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
            target_apps=body.target_apps,
            hint_enabled=body.hint_enabled,
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
    # Phase 4 + 9 — auto-monitor 활성화 (bastion / claude 모두)
    if b.monitor in ("bastion", "claude"):
        auto_monitor.start(battle_id)
    s = await session.get(Scenario, b.scenario_id) if b.scenario_id else None
    return _serialize(b, s.title if s else None)


def _manual_reasoning(*, user_name: str, ev_type: str, target: str,
                      points: int, description: str) -> str:
    """수동 이벤트의 자연어 채점 근거 (LLM 호출 없이 휴리스틱)."""
    side = "공격(Red)" if ev_type in ("attack", "exploit") else \
           "방어(Blue)" if ev_type in ("defend", "detect", "block", "alert") else "기타"
    sign = "+" if points > 0 else ""
    head = f"**수동 이벤트 — {side}**"
    if points == 0:
        head = f"**수동 이벤트 — {side} (정보성)**"
    body = (
        f"- 행위자: `{user_name}`\n"
        f"- 행동: `{ev_type}` on `{target or '(미지정)'}`\n"
        f"- 보고 점수: **{sign}{points}**\n"
        f"- 행위자 설명: {description or '(없음)'}\n\n"
        "_이 이벤트는 학생/관리자가 직접 보고한 내용입니다. 자동 검증은 수행되지 않았으며, "
        "관전자/심판은 행위자 설명과 점수의 적절성을 직접 판단해야 합니다._"
    )
    return f"{head}\n\n{body}"


@router.post("/{battle_id}/events", response_model=BattleEventOut, status_code=201)
async def post_event(
    battle_id: int,
    body: BattleEventIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> BattleEventOut:
    if user.role != "admin" and not await bs.is_participant(session, battle_id, user.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only participants or admin can post events")
    reasoning = _manual_reasoning(
        user_name=user.name, ev_type=body.event_type, target=body.target,
        points=body.points, description=body.description,
    )
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
            reasoning=reasoning,
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


# ── 힌트 ────────────────────────────────────────────
from pydantic import BaseModel, Field


class HintIn(BaseModel):
    mission_side: str = Field(default="any", pattern=r"^(red|blue|any)$")
    note: str = Field(default="", max_length=500)


class HintOut(BaseModel):
    text: str
    model: str
    cache_hit: bool
    cost_usd: float
    cooldown_remaining_sec: float


@router.post("/{battle_id}/hint", response_model=HintOut)
async def request_hint(
    battle_id: int,
    body: HintIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> HintOut:
    b = await session.get(Battle, battle_id)
    if not b:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "battle not found")
    if user.role != "admin" and not await bs.is_participant(session, battle_id, user.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only participants or admin can request hints")
    try:
        hr = await hint_svc.request_hint(
            session, battle=b, user_id=user.id,
            mission_side=body.mission_side, note=body.note,
        )
    except ValueError as e:
        msg = str(e)
        if msg.startswith("cooldown"):
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, msg,
                                headers={"Retry-After": "60"})
        raise HTTPException(status.HTTP_400_BAD_REQUEST, msg)
    return HintOut(
        text=hr.text, model=hr.model, cache_hit=hr.cache_hit,
        cost_usd=hr.cost_usd,
        cooldown_remaining_sec=hint_svc.cooldown_remaining(battle_id, user.id),
    )


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
    # Phase 9: 인증된 사용자는 누구나 read-only 관전 가능. 이벤트 push 는 별도 endpoint.
    async with SessionLocal() as s0:
        b0 = await s0.get(Battle, battle_id)
        if not b0:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "battle not found")

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
        "reasoning": e.reasoning,
        "points": e.points,
    }
