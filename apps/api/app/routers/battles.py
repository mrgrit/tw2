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
    BattleCreateIn, BattleDetail, BattleEventIn, BattleEventOut, BattleJoinIn,
    BattleOut, BattleParticipantOut, MissionOut,
)
from ..security import get_current_user, require_admin
from ..services import auto_monitor, battle_service as bs, hints as hint_svc
from ..services import event_analyzer as ea

router = APIRouter(prefix="/battles", tags=["battles"])


def _solved_orders(events: list, side_marker: str) -> set[int]:
    """auto-monitor 가 매칭한 (auto detect) blue 미션의 order 집합. red 는 수동 이벤트의
    target_vm 과 매칭되는 score 이벤트가 있으면 solved 로 본다."""
    out: set[int] = set()
    for e in events:
        d = e.detail or {}
        if side_marker == "blue":
            if d.get("source") == "auto_monitor" and d.get("blue_mission_order"):
                out.add(int(d["blue_mission_order"]))
        # red 는 일단 자동 검증이 없으므로 비워둠 (학생이 수동 보고)
    return out


def _missions_for_side(scenario, side: str, solved: set[int]) -> list[MissionOut]:
    if not scenario:
        return []
    container = (scenario.mission_red if side == "red" else scenario.mission_blue) or {}
    items = container.get("missions") or []
    # dry_run refined_expect 가 있으면 우선
    dry = (scenario.scoring or {}).get("dry_run", {}) or {}
    review_key = "red_review" if side == "red" else "blue_review"
    refined: dict[int, str] = {}
    for r in (dry.get("review", {}) or {}).get(review_key, []) or []:
        if r.get("order") is not None and r.get("refined_expect"):
            refined[int(r["order"])] = r["refined_expect"]

    out: list[MissionOut] = []
    for m in items:
        order = int(m.get("order") or 0)
        verify = m.get("verify") or {}
        sem = verify.get("semantic") or {}
        # expect 가 list 인 시나리오도 있음 → join
        raw_expect = refined.get(order) or verify.get("expect")
        if isinstance(raw_expect, list):
            expect_str = ", ".join(str(x) for x in raw_expect) if raw_expect else None
        else:
            expect_str = str(raw_expect) if raw_expect else None
        out.append(MissionOut(
            side=side, order=order,
            title=m.get("title"),
            instruction=str(m.get("instruction") or ""),
            target_vm=m.get("target_vm"),
            points=int(m.get("points") or 0),
            hint=m.get("hint"),
            verify_expect=expect_str,
            semantic_intent=sem.get("intent"),
            success_criteria=list(sem.get("success_criteria") or []),
            solved=order in solved,
        ))
    return sorted(out, key=lambda m: m.order)


async def _serialize_with_missions(
    session: AsyncSession, b: Battle, viewer_user_id: int,
) -> BattleDetail:
    elapsed, remaining = bs.battle_elapsed(b)
    title = None
    scenario = None
    if b.scenario_id:
        scenario = await session.get(Scenario, b.scenario_id)
        title = scenario.title if scenario else None

    my_role: str | None = None
    for p in b.participants:
        if p.user_id == viewer_user_id:
            my_role = p.role
            break

    blue_solved = _solved_orders(b.events, "blue")
    red_solved = _solved_orders(b.events, "red")
    red_missions = _missions_for_side(scenario, "red", red_solved)
    blue_missions = _missions_for_side(scenario, "blue", blue_solved)

    if my_role == "red":
        my_m, opp_m = red_missions, blue_missions
    elif my_role == "blue":
        my_m, opp_m = blue_missions, red_missions
    elif my_role in ("solo", "free"):
        # 혼자 / FFA — 양쪽 모두 본인 미션
        my_m, opp_m = red_missions + blue_missions, []
    else:
        # 관전자 (또는 admin) — 양쪽 모두 노출
        my_m, opp_m = [], red_missions + blue_missions

    return BattleDetail(
        battle=BattleOut.model_validate(b),
        scenario_title=title,
        participants=[BattleParticipantOut.model_validate(p) for p in b.participants],
        events=[BattleEventOut.model_validate(e) for e in b.events],
        elapsed_sec=round(elapsed, 1),
        remaining_sec=round(remaining, 1),
        my_role=my_role,
        my_missions=my_m,
        opponent_missions=opp_m,
    )


def _serialize(b: Battle, scenario_title: str | None) -> BattleDetail:
    """legacy — 빈 mission. 새 코드는 _serialize_with_missions 를 쓰도록."""
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
    return await _serialize_with_missions(session, b, viewer_user_id=user.id)


# ── Create / start / end ────────────────────────────
@router.post("", response_model=BattleDetail, status_code=201)
async def create_battle(
    body: BattleCreateIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> BattleDetail:
    parts = [p.model_dump() for p in body.participants]
    # admin 은 lobby (참가자 0명) 로 만들 수 있음
    is_admin = user.role == "admin"
    allow_lobby = is_admin and len(parts) == 0

    # solo 는 lobby 불가 (혼자 모드라 의미 없음). 본인 강제.
    if body.mode == "solo":
        if not parts:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "solo battle requires self as participant")
        if not is_admin and parts[0]["user_id"] != user.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "solo battle must include yourself only")
    # duel/ffa 비-admin: 자기 자신 포함 필수
    if body.mode in ("duel", "ffa") and not is_admin:
        if not parts or user.id not in {p["user_id"] for p in parts}:
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
            allow_lobby=allow_lobby,
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))

    return await _serialize_with_missions(session, b, viewer_user_id=user.id)


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
    if b.monitor in ("bastion", "claude"):
        auto_monitor.start(battle_id)
    return await _serialize_with_missions(session, b, viewer_user_id=user.id)


# ── 로비 join / leave ───────────────────────────────
@router.post("/{battle_id}/join", response_model=BattleDetail)
async def join_battle(
    battle_id: int,
    body: BattleJoinIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> BattleDetail:
    try:
        b = await bs.join_battle(
            session, battle_id=battle_id, user_id=user.id,
            role=body.role, infra_id=body.infra_id,
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    return await _serialize_with_missions(session, b, viewer_user_id=user.id)


@router.post("/{battle_id}/leave", response_model=BattleDetail)
async def leave_battle(
    battle_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> BattleDetail:
    try:
        b = await bs.leave_battle(session, battle_id=battle_id, user_id=user.id)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    return await _serialize_with_missions(session, b, viewer_user_id=user.id)


def _build_mission_context(scenario: Scenario | None, side: str | None,
                           order: int | None) -> ea.MissionContext | None:
    """시나리오 + (side, order) → MissionContext. 없으면 None."""
    if not scenario or not side or not order:
        return None
    container = (scenario.mission_red if side == "red" else scenario.mission_blue) or {}
    items = container.get("missions") or []
    raw = next((m for m in items if int(m.get("order") or 0) == order), None)
    if not raw:
        return None
    verify = raw.get("verify") or {}
    sem = verify.get("semantic") or {}
    expect = verify.get("expect")
    if isinstance(expect, list):
        expect = ", ".join(str(x) for x in expect) if expect else None
    return ea.MissionContext(
        side=side, order=order,
        instruction=str(raw.get("instruction") or ""),
        target_vm=raw.get("target_vm"),
        points=int(raw.get("points") or 0),
        hint=raw.get("hint"),
        verify_expect=str(expect) if expect else None,
        semantic_intent=sem.get("intent"),
        success_criteria=list(sem.get("success_criteria") or []),
        acceptable_methods=list(sem.get("acceptable_methods") or []),
        negative_signs=list(sem.get("negative_signs") or []),
    )


def _build_scenario_context(scenario: Scenario | None) -> ea.ScenarioContext | None:
    if not scenario:
        return None
    return ea.ScenarioContext(
        title=scenario.title or "",
        description=scenario.description or "",
        course_ref=scenario.course_ref,
    )


@router.post("/{battle_id}/events", response_model=BattleEventOut, status_code=201)
async def post_event(
    battle_id: int,
    body: BattleEventIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> BattleEventOut:
    if user.role != "admin" and not await bs.is_participant(session, battle_id, user.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only participants or admin can post events")

    # battle + scenario 로드 — analyzer 컨텍스트
    battle = await session.get(Battle, battle_id)
    if not battle:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "battle not found")
    scenario = await session.get(Scenario, battle.scenario_id) if battle.scenario_id else None

    # mission_side 추론: 명시 안 됐으면 event_type 으로 추정 (red/blue 배타)
    side = body.mission_side
    if side is None:
        if body.event_type in ("attack", "exploit"):
            side = "red"
        elif body.event_type in ("defend", "detect", "block", "alert"):
            side = "blue"

    mission_ctx = _build_mission_context(scenario, side, body.mission_order)
    scenario_ctx = _build_scenario_context(scenario)

    report = ea.StudentReport(
        user_name=user.name,
        event_type=body.event_type,
        target=body.target,
        points_claimed=body.points,
        description=body.description,
        what_i_did=body.what_i_did,
        what_happened=body.what_happened,
    )
    analysis = await ea.analyze_event(
        monitor=battle.monitor or "bastion",
        report=report,
        mission=mission_ctx,
        scenario=scenario_ctx,
    )

    # detail 에 학생 입력 + 분석 메타 모두 보존 (raw detail 도 진짜 데이터)
    detail = dict(body.detail or {})
    detail["report"] = {
        "what_i_did": body.what_i_did,
        "what_happened": body.what_happened,
        "mission_order": body.mission_order,
        "mission_side": side,
    }
    detail["analysis"] = {
        "model": analysis.model,
        "cost_usd": analysis.cost_usd,
        "criteria_met": analysis.criteria_met,
        "criteria_missing": analysis.criteria_missing,
        "negative_signs_hit": analysis.negative_signs_hit,
    }

    try:
        ev = await bs.add_event(
            session,
            battle_id=battle_id,
            actor_user_id=user.id,
            event_type=body.event_type,
            target=body.target,
            description=body.description,
            points=body.points,
            detail=detail,
            reasoning=analysis.reasoning,
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
    return await _serialize_with_missions(session, b, viewer_user_id=user.id)


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
    return await _serialize_with_missions(session, b, viewer_user_id=admin.id)


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
