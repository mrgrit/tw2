"""공방전 라우터 — Phase 2: solo / duel / ffa, 이벤트 push, SSE 스트림.

Phase 4 (Claude Code monitor) 에서는 별도 background task 가 자동으로
add_event 를 호출. 본 라우터는 manual + 자동 두 경로 모두 통과.
"""
from __future__ import annotations
import asyncio
import json
import os
from typing import AsyncIterator
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..db import SessionLocal, get_session
from ..models import (
    Battle, BattleEvent, BattleParticipant, Cohort, Infra, Scenario,
    StudentSubmission, User,
)
from ..schemas import (
    BattleCreateIn, BattleDetail, BattleEventIn, BattleEventOut, BattleJoinIn,
    BattleOut, BattleParticipantOut, MissionOut, StudentSubmissionOut,
)
from ..security import get_current_user, require_admin
from ..services import auto_monitor, battle_service as bs, hints as hint_svc
from ..services import event_analyzer as ea
from ..services import lab_monitor, provisioner
from ..services import feedback as fb_svc
from ..services import assessor_client, battlefield
from ..services import check_compiler as cc
from ..services import graders
from ..services import siem_export
from ..services import cohort_service as cs
import datetime as _dt

router = APIRouter(prefix="/battles", tags=["battles"])

# 제출 채점을 인라인으로 돌릴지(테스트=결정론) 백그라운드로 돌릴지(운영=비차단).
_GRADE_SYNC = os.getenv("TUBEWAR_GRADE_SYNC") == "1"
# 백그라운드 채점 태스크 — GC 로 사라지지 않도록 레퍼런스 보관.
_bg_tasks: set = set()


def _spawn(coro) -> None:
    t = asyncio.create_task(coro)
    _bg_tasks.add(t)
    t.add_done_callback(_bg_tasks.discard)


def _solved_orders(events: list, side_marker: str) -> set[int]:
    """auto-monitor(Assessor) 가 매칭한 미션 order 집합.

    blue/red 둘 다 detail.source=="auto_monitor" + "{side}_mission_order" 로 표기된다
    (red 는 cross-infra assess_target=opponent 채점 결과 포함)."""
    out: set[int] = set()
    key = f"{side_marker}_mission_order"
    for e in events:
        d = e.detail or {}
        if d.get("source") == "auto_monitor" and d.get(key):
            out.add(int(d[key]))
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
            checks=list(verify.get("checks") or []),
            assess_target="opponent" if str(m.get("assess_target") or "").lower() == "opponent" else "self",
            arm_rule=m.get("arm_rule"),
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
    # 시나리오 제목 / 코호트 이름을 배치 조회(N+1 방지)해 목록에 의미있는 이름 제공.
    sc_ids = {r.scenario_id for r in rows if r.scenario_id}
    co_ids = {r.cohort_id for r in rows if r.cohort_id}
    sc_titles = dict((await session.execute(
        select(Scenario.id, Scenario.title).where(Scenario.id.in_(sc_ids))
    )).all()) if sc_ids else {}
    co_names = dict((await session.execute(
        select(Cohort.id, Cohort.name).where(Cohort.id.in_(co_ids))
    )).all()) if co_ids else {}
    out: list[BattleOut] = []
    for r in rows:
        o = BattleOut.model_validate(r)
        o.scenario_title = sc_titles.get(r.scenario_id)
        o.cohort_name = co_names.get(r.cohort_id)
        out.append(o)
    return out


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
            cohort_id=body.cohort_id,
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
    # (옵션) 룰 무장 — 기본 skip(no-op).
    await provisioner.arm_battle_rules(session, battle_id)
    # (옵션) 백그라운드 실습 모니터 — 기본 OFF(env TUBEWAR_LAB_MONITOR=1 일 때만).
    if lab_monitor.autostart_enabled():
        lab_monitor.start(battle_id, feedback_cb=fb_svc.bottleneck_feedback_cb)
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


def _raw_mission(scenario: Scenario | None, side: str | None, order: int | None) -> dict | None:
    if not scenario or not side or not order:
        return None
    container = (scenario.mission_red if side == "red" else scenario.mission_blue) or {}
    return next((m for m in (container.get("missions") or [])
                 if int(m.get("order") or 0) == order), None)


async def _role_infra_map(session: AsyncSession, battle_id: int) -> tuple[dict[str, Infra], dict[int, Infra]]:
    """role('red'/'blue') → Infra (solo/free 는 양쪽) + user_id → Infra."""
    parts = (await session.scalars(
        select(BattleParticipant).where(BattleParticipant.battle_id == battle_id)
    )).all()
    role_infra: dict[str, Infra] = {}
    user_infra: dict[int, Infra] = {}
    for p in parts:
        inf = await session.get(Infra, p.infra_id) if p.infra_id else None
        if not inf:
            continue
        user_infra[p.user_id] = inf
        if p.role in ("red", "blue"):
            role_infra[p.role] = inf
        elif p.role in ("solo", "free"):
            role_infra.setdefault("red", inf)
            role_infra.setdefault("blue", inf)
    return role_infra, user_infra


async def _initial_evidence(actor_infra, target_infra, mission_raw: dict | None,
                            side: str | None, external: bool = False) -> str:
    """AI 채점 초기 grounding — 학생이 **실제 실행한 명령/활동**(/activity) + 미션 check 상태.
    AI 는 이후 inspector 로 추가 점검을 직접 요청한다. 학생 말만 믿지 않는 읽기전용 교차검증.

    external=True(외부/cross-infra 공격)면 6v6 의 외부 attacker(attacker-ext) 명령은 수집이
    불완전하므로, 타깃(상대) 인프라의 공격 흔적(WAF/IPS/Wazuh/접근로그 + source IP·payload)을
    1차 근거로 삼으라는 caveat 를 명시한다."""
    lines: list[str] = []
    if external:
        lines.append("[외부/cross-infra 공격: 외부 attacker(attacker-ext) 명령 로그는 6v6 에서 수집이 "
                     "불완전함 → command_ran(attacker-ext) 신뢰 금지. 아래 '타깃 인프라' 공격 흔적과 "
                     "source IP·payload 상관으로 판정할 것.]")
    if actor_infra:
        act = await assessor_client.activity(actor_infra, want=["commands", "alerts", "fim", "services"],
                                             since_sec=3600, timeout=5.0)
        if act.get("ok"):
            cmds = act.get("commands") or []
            hdr = (f"[내부 attacker 명령 {len(cmds)}건 — 참고(외부 attacker 명령은 미수집일 수 있음)]"
                   if external else f"[학생이 실제 실행한 최근 명령 {len(cmds)}건 — 핵심 증거]")
            lines.append(hdr)
            for c in cmds[:40]:
                lines.append(f"  $ {c.get('cmd') if isinstance(c, dict) else c}")
            if act.get("fim"):
                lines.append(f"[파일변경 {len(act['fim'])}건] " + json.dumps(act["fim"][:5], ensure_ascii=False, default=str))
            if act.get("alerts"):
                lines.append(f"[최근 알림 {len(act['alerts'])}건]")
        else:
            lines.append(f"[학생 인프라 활동 수집 실패: {act.get('error')}]")
    else:
        lines.append("[학생 인프라 미등록 — 명령 증거 없음]")

    if mission_raw and side and target_infra:
        checks = cc.compile_mission_checks(dict(mission_raw), side=side)
        resp = await assessor_client.assess(target_infra, checks, timeout=5.0)
        if resp.get("ok"):
            lines.append("[타깃(상대) 인프라 공격 흔적 — 외부 공격의 핵심 증거. source IP·payload 상관 확인]"
                         if external else
                         "[미션 check 상태 — 참고용. 앰비언트(타인이 만든 상태)일 수 있으니 학생 행위 증거와 함께 판단]")
            for r in resp.get("results", []):
                lines.append(f"  {r.get('id')}: passed={r.get('passed')} | {str(r.get('evidence'))[:120]}")
    return "\n".join(lines)


@router.post("/{battle_id}/events", response_model=StudentSubmissionOut, status_code=201)
async def post_event(
    battle_id: int,
    body: BattleEventIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> StudentSubmissionOut:
    """학생 제출 → **즉시 저널(verbatim) 보존 + 곧장 반환**, 채점은 비동기.

    흐름: 제출하면 입력을 그대로 StudentSubmission(pending) 에 영속화하고 바로 응답한다.
    학생은 채점을 기다리지 않고 다음 미션으로 넘어갈 수 있다. AI 시맨틱 채점 + 인프라 점검은
    백그라운드(`grade_submission`)에서 동시성 제한 큐로 처리되어, 끝나면 같은 행에 verdict/점수/
    피드백을 붙이고 battle_event(점수 권위)를 생성한다.

    - 점수는 **AI 가 증거 기반으로 결정**(학생 claim 무시). 미션 미지정은 admin 수동 보정/학생 0점.
    - `client_token` 으로 더블클릭/재전송 멱등 — 같은 토큰이면 기존 제출 반환(중복 채점 금지).
    - 테스트(`TUBEWAR_GRADE_SYNC=1`)에서는 인라인 채점으로 결정론 보장.
    """
    is_admin = user.role == "admin"
    if not is_admin and not await bs.is_participant(session, battle_id, user.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only participants or admin can post events")

    battle = await session.get(Battle, battle_id)
    if not battle:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "battle not found")
    if battle.status != "active":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"battle is {battle.status}, not active")

    # 멱등 — 같은 client_token 이면 기존 제출 반환(더블클릭/재전송 무해화).
    if body.client_token:
        existing = (await session.scalars(select(StudentSubmission).where(
            StudentSubmission.user_id == user.id,
            StudentSubmission.client_token == body.client_token))).first()
        if existing:
            return StudentSubmissionOut.model_validate(existing)

    scenario = await session.get(Scenario, battle.scenario_id) if battle.scenario_id else None
    side = body.mission_side
    if side is None:
        if body.event_type in ("attack", "exploit"):
            side = "red"
        elif body.event_type in ("defend", "detect", "block", "alert"):
            side = "blue"

    # 제출 당시 학생이 본 미션 지시문 사본(시나리오가 나중에 바뀌어도 복습 맥락 보존).
    mission_raw = _raw_mission(scenario, side, body.mission_order)
    snapshot: dict = {}
    if mission_raw:
        snapshot = {
            "title": scenario.title if scenario else None,
            "side": side, "order": body.mission_order,
            "points": mission_raw.get("points"), "target_vm": mission_raw.get("target_vm"),
            "instruction": mission_raw.get("instruction", ""),
        }

    sub = StudentSubmission(
        user_id=user.id, battle_id=battle_id, scenario_id=battle.scenario_id,
        cohort_id=battle.cohort_id, mission_side=side, mission_order=body.mission_order,
        event_type=body.event_type, target=body.target,
        what_i_did=body.what_i_did, what_happened=body.what_happened,
        description=body.description, claimed_points=body.points,
        mission_snapshot=snapshot, grade_status="pending", client_token=body.client_token,
    )
    session.add(sub)
    try:
        await session.commit()
    except IntegrityError:
        # 동시 더블클릭 레이스 — 같은 토큰이 먼저 커밋됨. 기존 것 반환.
        await session.rollback()
        existing = (await session.scalars(select(StudentSubmission).where(
            StudentSubmission.user_id == user.id,
            StudentSubmission.client_token == body.client_token))).first()
        if existing:
            return StudentSubmissionOut.model_validate(existing)
        raise
    await session.refresh(sub)
    sub_id = sub.id

    if _GRADE_SYNC:
        await grade_submission(sub_id)     # 테스트/동기 모드 — 인라인 채점
        await session.refresh(sub)
    else:
        _spawn(grade_submission(sub_id))   # 운영 — 비차단(학생은 바로 다음 미션)
    return StudentSubmissionOut.model_validate(sub)


async def grade_submission(submission_id: int) -> None:
    """제출 1건을 채점하고 결과를 같은 행 + battle_event(점수 권위)에 반영. **자체 세션** 사용.

    제출(verbatim)은 이미 영속화돼 있으므로, 채점이 느리거나 실패해도 입력은 보존된다.
    실패 시 grade_status='failed' 로 표시(강사 검토). 비동기/인라인 양쪽에서 공용.
    """
    async with SessionLocal() as session:
        sub = await session.get(StudentSubmission, submission_id)
        if sub is None:
            return
        battle = await session.get(Battle, sub.battle_id) if sub.battle_id else None
        scenario = await session.get(Scenario, sub.scenario_id) if sub.scenario_id else None
        actor = await session.get(User, sub.user_id)
        side = sub.mission_side
        report = ea.StudentReport(
            user_name=(actor.name if actor else ""), event_type=sub.event_type, target=sub.target,
            points_claimed=sub.claimed_points, description=sub.description,
            what_i_did=sub.what_i_did, what_happened=sub.what_happened,
        )
        mission_ctx = _build_mission_context(scenario, side, sub.mission_order)
        scenario_ctx = _build_scenario_context(scenario)
        mission_raw = _raw_mission(scenario, side, sub.mission_order)
        is_admin = bool(actor and actor.role == "admin")
        actor_infra = None
        evidence_summary = ""
        max_points: int | None = None

        try:
            if mission_ctx is not None and battle is not None:
                # ── AI 가 참여자/타깃 인프라를 직접 점검 → 시맨틱 채점(점수는 AI 결정) ──
                role_infra, user_infra = await _role_infra_map(session, battle.id)
                actor_infra = user_infra.get(sub.user_id)
                assess_target = battlefield.normalize_assess_target((mission_raw or {}).get("assess_target"))
                target_infra = battlefield.resolve_target_infra(side or "blue", assess_target, role_infra) or actor_infra
                evidence = await _initial_evidence(actor_infra, target_infra, mission_raw, side,
                                                   external=(assess_target == "opponent"))

                async def _inspect(checks: list[dict]) -> list[dict]:
                    inf = target_infra or actor_infra
                    if not inf:
                        return [{"error": "no infra to inspect"}]
                    resp = await assessor_client.assess(inf, checks, timeout=6.0)
                    return resp.get("results", []) if resp.get("ok") else [{"error": resp.get("error")}]

                grader_cfg = await graders.resolve_for_scenario(session, scenario)
                analysis = await ea.grade(
                    report=report, mission=mission_ctx, scenario=scenario_ctx,
                    evidence_text=evidence, max_points=mission_ctx.points,
                    inspector=(_inspect if (target_infra or actor_infra) else None),
                    grader=grader_cfg,
                )
                awarded = max(0, min(int(analysis.awarded_points or 0), mission_ctx.points))  # [0,max]
                evidence_summary = evidence[:1500]
                max_points = mission_ctx.points
            else:
                # 미션 미지정 — AI 채점 대상 아님. admin 만 수동 점수 보정.
                analysis = await ea.analyze_event(
                    monitor=(battle.monitor if battle else "bastion") or "bastion",
                    report=report, mission=None, scenario=scenario_ctx)
                awarded = int(sub.claimed_points) if is_admin else 0
        except Exception as e:  # 채점기/인프라 오류 — 입력은 보존, 강사 검토 대상으로 표시.
            sub.grade_status = "failed"
            sub.feedback = f"채점 실패(강사 검토 대상): {e}"
            sub.graded_at = _dt.datetime.now(_dt.timezone.utc)
            await session.commit()
            return

        # ── 점수 권위 기록(battle_event) — 배틀이 아직 active 일 때만 점수 반영 ──
        detail = {
            "report": {"what_i_did": sub.what_i_did, "what_happened": sub.what_happened,
                       "mission_order": sub.mission_order, "mission_side": side},
            "grading": {
                "model": analysis.model, "verdict": getattr(analysis, "verdict", "review"),
                "claimed_points": sub.claimed_points, "awarded_points": awarded,
                "ai_decided": mission_ctx is not None, "cost_usd": analysis.cost_usd,
                "criteria_met": analysis.criteria_met, "criteria_missing": analysis.criteria_missing,
                "evidence": evidence_summary,
            },
        }
        event_id = None
        if battle is not None:
            try:
                ev = await bs.add_event(
                    session, battle_id=battle.id, actor_user_id=sub.user_id,
                    event_type=sub.event_type, target=sub.target, description=sub.description,
                    points=awarded, detail=detail, reasoning=analysis.reasoning,
                )
                event_id = ev.id
            except ValueError:
                event_id = None   # 배틀이 채점 완료 전 종료 — 점수 미반영, 저널엔 결과 보존.

        sub.grade_status = "graded"
        sub.verdict = getattr(analysis, "verdict", "review")
        sub.awarded_points = awarded
        sub.max_points = max_points
        sub.feedback = analysis.reasoning
        sub.criteria_met = analysis.criteria_met or []
        sub.criteria_missing = analysis.criteria_missing or []
        sub.grader_model = analysis.model
        sub.battle_event_id = event_id
        sub.graded_at = _dt.datetime.now(_dt.timezone.utc)
        await session.commit()

        # ── 채점 결과(제출+verdict+피드백)를 중앙 SIEM 에 영구 보존 → 강사 실시간 모니터링.
        if mission_ctx is not None and battle is not None and siem_export.is_enabled():
            try:
                chain = await cs.ancestor_chain(session, battle.cohort_id) if battle.cohort_id else []
                grade_doc = {
                    "battle_id": battle.id, "user_id": sub.user_id,
                    "user_name": (actor.name if actor else ""),
                    "infra_id": getattr(actor_infra, "id", None), "kind": "grade",
                    "scenario_id": sub.scenario_id,
                    "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(),
                    "scenario_step": f"{side}-{sub.mission_order}",
                    "payload": {
                        "mission_side": side, "mission_order": sub.mission_order,
                        "verdict": getattr(analysis, "verdict", "review"),
                        "claimed_points": sub.claimed_points, "awarded_points": awarded,
                        "max_points": max_points,
                        "what_i_did": (sub.what_i_did or "")[:1000],
                        "what_happened": (sub.what_happened or "")[:1000],
                        "feedback": (analysis.reasoning or "")[:1500],
                        "model": analysis.model,
                        "criteria_met": analysis.criteria_met,
                        "criteria_missing": analysis.criteria_missing,
                    },
                }
                await siem_export.export_events(siem_export.default_client(), [grade_doc], chain)
            except Exception:
                pass  # SIEM 전송 실패는 채점을 막지 않음(best-effort)


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
    lab_monitor.stop(battle_id)
    await provisioner.withdraw_battle_rules(session, battle_id)
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
