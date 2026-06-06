"""실습 모니터링 라우터 — 진도 대시보드, 활동 타임라인, lab-tick, 중앙 SIEM 딥링크.

채점(battles)과 별개 트랙. 진도/병목 산출은 결정론(LLM 0), 피드백 작성만 CC.
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import ActivityEvent, Battle, GraderProfile, Scenario, User
from ..schemas import ActivityEventOut, CohortProgressOut, StudentProgressOut
from ..security import get_current_user, require_admin
from ..services import lab_monitor, siem_export
from ..services import cohort_service as cs
from ..services import event_analyzer as ea
from ..services import feedback as fb_svc
from ..services import graders

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


@router.get("/battles/{battle_id}/progress", response_model=CohortProgressOut)
async def battle_progress(
    battle_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> CohortProgressOut:
    """학생×step 진도 매트릭스 + 병목 하이라이트 (읽기 전용 계산)."""
    b = await session.get(Battle, battle_id)
    if not b:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "battle not found")
    rows = await lab_monitor.compute_progress(session, battle_id, persist=False)
    uids = [r["user_id"] for r in rows]
    names = {
        u.id: u.name for u in (await session.scalars(
            select(User).where(User.id.in_(uids))
        )).all()
    } if uids else {}
    students = [StudentProgressOut(
        user_id=r["user_id"], name=names.get(r["user_id"]),
        completion=r["completion"], steps_done=r["steps_done"], steps_total=r["steps_total"],
        bottleneck_flags=r["bottleneck_flags"], stuck=r["stuck"],
    ) for r in rows]
    steps_total = max((r["steps_total"] for r in rows), default=0)
    return CohortProgressOut(cohort_id=b.cohort_id, battle_id=battle_id,
                             steps_total=steps_total, students=students)


@router.get("/battles/{battle_id}/activity", response_model=list[ActivityEventOut])
async def battle_activity(
    battle_id: int,
    user_id: int | None = None,
    limit: int = 200,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[ActivityEventOut]:
    """활동 타임라인 드릴다운."""
    q = select(ActivityEvent).where(ActivityEvent.battle_id == battle_id)
    if user_id is not None:
        q = q.where(ActivityEvent.user_id == user_id)
    q = q.order_by(ActivityEvent.id.desc()).limit(min(max(limit, 1), 1000))
    rows = (await session.scalars(q)).all()
    return [ActivityEventOut.model_validate(r) for r in rows]


@router.post("/battles/{battle_id}/lab-tick")
async def lab_tick(
    battle_id: int,
    with_feedback: bool = False,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """lab_monitor 1 tick 즉시 실행(폴링 대기 없이). with_feedback 면 막힌 학생에게 CC 피드백."""
    b = await session.get(Battle, battle_id)
    if not b:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "battle not found")
    cb = fb_svc.bottleneck_feedback_cb if with_feedback else None
    return await lab_monitor.run_lab_tick(battle_id, feedback_cb=cb)


class SiemSearchOut(BaseModel):
    enabled: bool
    index: str | None = None
    cohort_path: str | None = None
    dashboards_deeplink: str | None = None
    docs: list[dict] = []
    note: str | None = None


_SIEM_DISABLED_NOTE = "중앙 SIEM 미설정(OPENSEARCH_URL). 활동은 Postgres/실습 모니터링에서 확인 가능."


@router.get("/siem/search", response_model=SiemSearchOut)
async def siem_search(
    cohort_id: int | None = None,
    limit: int = 100,
    q: str | None = None,
    scenario_id: int | None = None,
    student: int | None = None,
    kind: str | None = None,
    time_from: str | None = None,
    time_to: str | None = None,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> SiemSearchOut:
    """중앙 SIEM(OpenSearch) 활동을 tubewar 안에서 직접 조회(임베드).

    cohort_id 서브트리 + scenario_id/student/kind/기간(time_from~time_to ISO)으로 좁힌다.
    docs 의 각 항목은 full payload 를 포함 → UI 에서 행 클릭 시 풀 로그 표시.
    """
    chain = await cs.ancestor_chain(session, cohort_id) if cohort_id else []
    client = siem_export.default_client()
    if client is None:
        return SiemSearchOut(enabled=False, docs=[], note=_SIEM_DISABLED_NOTE)
    res = await siem_export.search_events(
        client, chain or None, limit=limit, q=q, scenario_id=scenario_id,
        student=student, kind=kind, time_from=time_from, time_to=time_to)
    return SiemSearchOut(
        enabled=True, index=res.get("index"),
        cohort_path=siem_export.cohort_path_str(chain) if chain else None,
        dashboards_deeplink=siem_export.dashboard_deeplink(chain) if chain else None,
        docs=res.get("docs", []),
    )


class SiemStatsOut(BaseModel):
    enabled: bool
    index: str | None = None
    total: int = 0
    by_kind: list[dict] = []
    by_student: list[dict] = []
    by_scenario: list[dict] = []
    by_day: list[dict] = []
    pivot: list[dict] = []   # 학생 × 종류 매트릭스
    note: str | None = None


async def _names_for(session: AsyncSession, ids: list[int]) -> dict[int, str | None]:
    ids = [i for i in ids if i is not None]
    if not ids:
        return {}
    return {u.id: u.name for u in (await session.scalars(
        select(User).where(User.id.in_(ids)))).all()}


@router.get("/siem/stats", response_model=SiemStatsOut)
async def siem_stats(
    cohort_id: int | None = None,
    scenario_id: int | None = None,
    student: int | None = None,
    kind: str | None = None,
    time_from: str | None = None,
    time_to: str | None = None,
    q: str | None = None,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> SiemStatsOut:
    """로그 테이블 위 주요 통계 — 총건수 / 종류별 / 학생별 / 일자별(시계열)."""
    chain = await cs.ancestor_chain(session, cohort_id) if cohort_id else []
    client = siem_export.default_client()
    if client is None:
        return SiemStatsOut(enabled=False, note=_SIEM_DISABLED_NOTE)
    res = await siem_export.aggregate(
        client, chain or None, scenario_id=scenario_id, student=student, kind=kind,
        time_from=time_from, time_to=time_to, q=q)
    pivot_ids = [b["student"] for b in res.get("pivot", [])]
    names = await _names_for(session, [b["student"] for b in res.get("by_student", [])] + pivot_ids)
    by_student = [{**b, "name": names.get(b.get("student"))} for b in res.get("by_student", [])]
    pivot = [{**b, "name": names.get(b.get("student"))} for b in res.get("pivot", [])]
    # 시나리오 제목 매핑
    from ..models import Scenario
    sc_ids = [b["scenario_id"] for b in res.get("by_scenario", []) if b.get("scenario_id") is not None]
    titles = dict((await session.execute(
        select(Scenario.id, Scenario.title).where(Scenario.id.in_(sc_ids))
    )).all()) if sc_ids else {}
    by_scenario = [{**b, "title": titles.get(b.get("scenario_id"))} for b in res.get("by_scenario", [])]
    return SiemStatsOut(
        enabled=True, index=res.get("index"), total=res.get("total", 0),
        by_kind=res.get("by_kind", []), by_student=by_student,
        by_scenario=by_scenario, by_day=res.get("by_day", []), pivot=pivot)


@router.get("/siem/scenarios")
async def siem_scenarios(
    cohort_id: int,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """코호트(서브트리) 의 공방전이 쓴 시나리오 + 미션 목록 — 시나리오/미션 레벨 드릴다운용."""
    ids = await cs.subtree_ids(session, cohort_id)
    if not ids:
        return {"cohort_id": cohort_id, "scenarios": []}
    battles = (await session.scalars(select(Battle).where(Battle.cohort_id.in_(ids)))).all()
    scn_ids = {b.scenario_id for b in battles if b.scenario_id}
    scns = (await session.scalars(
        select(Scenario).where(Scenario.id.in_(scn_ids)))).all() if scn_ids else []
    out = []
    for s in scns:
        missions = []
        for side, mb in (("red", s.mission_red), ("blue", s.mission_blue)):
            for m in (mb or {}).get("missions") or []:
                missions.append({"side": side, "order": m.get("order"),
                                 "instruction": (m.get("instruction") or "")[:140],
                                 "points": m.get("points")})
        missions.sort(key=lambda m: (m["side"], m.get("order") or 0))
        out.append({"scenario_id": s.id, "title": s.title,
                    "battle_ids": [b.id for b in battles if b.scenario_id == s.id],
                    "missions": missions})
    out.sort(key=lambda x: x["scenario_id"])
    return {"cohort_id": cohort_id, "scenarios": out}


@router.get("/siem/accomplishment")
async def siem_accomplishment(
    cohort_id: int,
    scenario_id: int | None = None,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """학생 달성도 매트릭스(주축) — AI 채점된 battle_events 기반. 출처/근거 교차검증된
    '누가 실제로 깼나'. 학생 × 미션단계 → 최신 verdict/점수/근거. (mission_check 와 달리
    앰비언트 노이즈에 안 흔들림.) scenario_id 주면 미제출 칸까지 표시."""
    from ..models import BattleEvent, Scenario
    ids = await cs.subtree_ids(session, cohort_id)
    if not ids:
        return {"students": [], "steps": [], "cells": {}, "points": {}}
    bq = select(Battle).where(Battle.cohort_id.in_(ids))
    if scenario_id is not None:
        bq = bq.where(Battle.scenario_id == scenario_id)
    battles = (await session.scalars(bq)).all()
    bids = [b.id for b in battles]
    steps: list[str] = []
    points: dict[str, int] = {}
    if scenario_id is not None:
        scn = await session.get(Scenario, scenario_id)
        if scn:
            for side, mb in (("red", scn.mission_red), ("blue", scn.mission_blue)):
                for m in (mb or {}).get("missions") or []:
                    st = f"{side}-{int(m.get('order') or 0)}"
                    steps.append(st); points[st] = m.get("points") or 0
    cells: dict[str, dict] = {}
    students: dict[int, str] = {}
    if bids:
        evs = (await session.scalars(
            select(BattleEvent).where(BattleEvent.battle_id.in_(bids)).order_by(BattleEvent.id))).all()
        for e in evs:
            rep = (e.detail or {}).get("report") or {}
            o, sd = rep.get("mission_order"), rep.get("mission_side")
            if o is None or sd is None:
                continue
            st = f"{sd}-{int(o)}"
            if st not in steps:
                steps.append(st)
            g = (e.detail or {}).get("grading") or {}
            students[e.actor_user_id] = ""
            cells[f"{e.actor_user_id}|{st}"] = {   # id 오름차순 → 마지막이 최신
                "verdict": g.get("verdict"), "points": e.points,
                "reasoning": (e.reasoning or "")[:600], "battle_id": e.battle_id,
            }
    names = await _names_for(session, list(students.keys()))
    steps.sort(key=lambda s: (s.split("-")[0], int(s.split("-")[1]) if "-" in s and s.split("-")[1].isdigit() else 0))
    return {"scenario_id": scenario_id,
            "students": [{"student": k, "name": names.get(k) or f"#{k}"} for k in students],
            "steps": steps, "points": points, "cells": cells}


@router.get("/siem/mission-checks")
async def siem_mission_checks(
    cohort_id: int,
    scenario_id: int | None = None,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """미션-체크 실시간 현황판 — lab_monitor 가 적재한 mission_check 문서를
    학생 × 미션단계(red-1, blue-2 …) 매트릭스(최신 통과/증거)로 환원."""
    chain = await cs.ancestor_chain(session, cohort_id) if cohort_id else []
    client = siem_export.default_client()
    if client is None:
        return {"enabled": False, "students": [], "steps": [], "cells": {}}
    res = await siem_export.search_events(
        client, chain or None, kind="mission_check", scenario_id=scenario_id, limit=500)
    docs = res.get("docs", [])
    # 최신 우선 정렬돼 옴 → (student, step) 첫 등장만 채택
    cells: dict[str, dict] = {}
    steps: list[str] = []
    students: dict[int, str] = {}
    for d in docs:
        p = d.get("payload") or {}
        step = d.get("scenario_step")
        sid = d.get("student")
        if step is None or sid is None:
            continue
        key = f"{sid}|{step}"
        if key in cells:
            continue
        if step not in steps:
            steps.append(step)
        students[sid] = d.get("student_name") or f"#{sid}"
        cells[key] = {"passed": bool(p.get("passed")), "evidence": str(p.get("evidence") or "")[:300],
                      "ts": d.get("ts"), "points": p.get("points"),
                      "check_type": p.get("check_type"), "volatile": bool(p.get("volatile"))}
    steps.sort(key=lambda s: (s.split("-")[0], int(s.split("-")[1]) if "-" in s and s.split("-")[1].isdigit() else 0))
    return {"enabled": True, "scenario_id": scenario_id,
            "students": [{"student": k, "name": v} for k, v in students.items()],
            "steps": steps, "cells": cells}


@router.get("/siem/mission")
async def siem_mission(
    cohort_id: int,
    scenario_id: int,
    side: str,
    order: int,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """미션 레벨 드릴다운 — 코호트의 해당 시나리오/미션에 대한 학생별 채점결과.

    battle_events 에서 detail.report.mission_(order|side) 가 일치하는 제출을 학생별로
    모아 최신 1건(통과/점수/AI 근거)을 반환. 시나리오→미션 아래 마지막 레벨.
    """
    from ..models import BattleEvent
    ids = await cs.subtree_ids(session, cohort_id)
    if not ids:
        return {"results": []}
    battles = (await session.scalars(
        select(Battle).where(Battle.cohort_id.in_(ids), Battle.scenario_id == scenario_id))).all()
    bids = [b.id for b in battles]
    if not bids:
        return {"results": []}
    evs = (await session.scalars(
        select(BattleEvent).where(BattleEvent.battle_id.in_(bids)).order_by(BattleEvent.id))).all()
    per: dict[int, dict] = {}
    for e in evs:
        rep = (e.detail or {}).get("report") or {}
        if rep.get("mission_order") == order and rep.get("mission_side") == side:
            g = (e.detail or {}).get("grading") or {}
            per[e.actor_user_id] = {   # 최신(id 오름차순 순회 → 마지막이 최신) 우선
                "student": e.actor_user_id, "points": e.points,
                "verdict": g.get("verdict"), "awarded": g.get("awarded_points"),
                "claimed": g.get("claimed_points"),
                "criteria_met": g.get("criteria_met") or [],
                "criteria_missing": g.get("criteria_missing") or [],
                "reasoning": e.reasoning or "", "battle_id": e.battle_id,
                "what_i_did": rep.get("what_i_did", ""),
            }
    names = await _names_for(session, list(per.keys()))
    results = [{**v, "name": names.get(v["student"])} for v in per.values()]
    results.sort(key=lambda r: -(r["points"] or 0))
    return {"cohort_id": cohort_id, "scenario_id": scenario_id, "side": side,
            "order": order, "results": results}


async def _compute_clears(session: AsyncSession, cohort_id: int,
                          scenario_id: int | None) -> list[dict]:
    """코호트(서브트리) 공방전들의 학생별 클리어(완수 미션) 집계 — Postgres 권위 채점 기준."""
    ids = await cs.subtree_ids(session, cohort_id)
    if not ids:
        return []
    battles = (await session.scalars(select(Battle).where(Battle.cohort_id.in_(ids)))).all()
    if scenario_id is not None:
        battles = [b for b in battles if b.scenario_id == scenario_id]
    agg: dict[int, dict] = {}
    for b in battles:
        rows = await lab_monitor.compute_progress(session, b.id, persist=False)
        for r in rows:
            a = agg.setdefault(r["user_id"], {"student": r["user_id"], "cleared": 0,
                                              "steps_total": 0, "battles": 0, "stuck": 0})
            a["cleared"] += r["steps_done"]
            a["steps_total"] += r["steps_total"]
            a["battles"] += 1
            a["stuck"] += 1 if r.get("stuck") else 0
    names = await _names_for(session, list(agg))
    out = list(agg.values())
    for o in out:
        o["name"] = names.get(o["student"])
        o["completion"] = round(100.0 * o["cleared"] / o["steps_total"], 1) if o["steps_total"] else 0.0
    out.sort(key=lambda x: (-x["cleared"], x["student"]))
    return out


@router.get("/siem/clears")
async def siem_clears(
    cohort_id: int,
    scenario_id: int | None = None,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """학생별 클리어(완수 미션) 수 + 완성도 — 시나리오로 좁히면 그 시나리오 한정."""
    return {"cohort_id": cohort_id, "scenario_id": scenario_id,
            "students": await _compute_clears(session, cohort_id, scenario_id)}


class SiemAskIn(BaseModel):
    question: str
    cohort_id: int | None = None
    scenario_id: int | None = None
    student: int | None = None
    kind: str | None = None
    time_from: str | None = None
    time_to: str | None = None
    grader_profile_id: int | None = None


class SiemAskOut(BaseModel):
    answer: str
    model: str
    used_logs: int
    used_clears: int
    cost_usd: float = 0.0


def _compact_doc(d: dict) -> dict:
    """AI 컨텍스트용 경량 로그 — payload 는 요약 문자열로."""
    p = d.get("payload") or {}
    summary = p.get("cmd") or p.get("description") or p.get("path") or p.get("rule_id") or p
    return {"ts": d.get("ts"), "student": d.get("student_name") or d.get("student"),
            "kind": d.get("kind"), "scenario_id": d.get("scenario_id"), "info": str(summary)[:200]}


@router.post("/siem/ask", response_model=SiemAskOut)
async def siem_ask(
    body: SiemAskIn,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> SiemAskOut:
    """이 페이지에서 강사가 AI에게 질문 → 로그/통계/클리어를 근거로 CC 또는 bastion 이 분석 답변."""
    chain = await cs.ancestor_chain(session, body.cohort_id) if body.cohort_id else []
    client = siem_export.default_client()
    stats: dict = {}
    logs: list[dict] = []
    if client is not None:
        agg = await siem_export.aggregate(
            client, chain or None, scenario_id=body.scenario_id, student=body.student,
            kind=body.kind, time_from=body.time_from, time_to=body.time_to)
        stats = {k: agg.get(k) for k in ("total", "by_kind", "by_student", "by_day")}
        sr = await siem_export.search_events(
            client, chain or None, limit=80, scenario_id=body.scenario_id,
            student=body.student, kind=body.kind, time_from=body.time_from, time_to=body.time_to)
        logs = [_compact_doc(d) for d in sr.get("docs", [])]
    clears = await _compute_clears(session, body.cohort_id, body.scenario_id) if body.cohort_id else []

    # AI/모델 선택 — grader_profile_id 우선, 없으면 기본 프로필 → CC fallback.
    grader = None
    if body.grader_profile_id:
        p = await session.get(GraderProfile, body.grader_profile_id)
        if p and p.enabled:
            grader = {"provider": p.provider, "model": p.model, "base_url": p.base_url,
                      "api_key": p.api_key, "name": p.name}
    if grader is None:
        grader = await graders.resolve_for_scenario(session, None)

    cohort_path = siem_export.cohort_path_str(chain) if chain else None
    context = {"cohort_path": cohort_path, "scenario_id": body.scenario_id,
               "period": {"from": body.time_from, "to": body.time_to},
               "stats": stats, "recent_logs": logs, "clears": clears}
    result = await ea.analyze_logs(body.question, context, grader)
    return SiemAskOut(answer=result.reasoning, model=result.model,
                      used_logs=len(logs), used_clears=len(clears),
                      cost_usd=getattr(result, "cost_usd", 0.0) or 0.0)


class SiemDeeplinkOut(BaseModel):
    cohort_id: int
    cohort_path: str
    deeplink: str | None
    provisioned: list[str]
    enabled: bool


@router.get("/cohorts/{cohort_id}/siem", response_model=SiemDeeplinkOut)
async def cohort_siem(
    cohort_id: int,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> SiemDeeplinkOut:
    """강사용 중앙 SIEM 딥링크 + (멱등) 데이터뷰/대시보드/RBAC 보장."""
    chain = await cs.ancestor_chain(session, cohort_id)
    if not chain:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "cohort not found")
    client = siem_export.default_client()   # 미설정이면 None → no-op
    result = await siem_export.ensure_cohort_objects(client, chain)
    return SiemDeeplinkOut(
        cohort_id=cohort_id,
        cohort_path=siem_export.cohort_path_str(chain),
        deeplink=siem_export.dashboard_deeplink(chain),
        provisioned=result.get("created", []),
        enabled=siem_export.is_enabled(),
    )
