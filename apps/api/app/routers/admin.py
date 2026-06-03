"""관리자 전용 라우터 — Claude Code 시나리오 생성, 시나리오 활성화, 강제 종료 등.

권한: 모든 엔드포인트 require_admin. Phase 5 에서 ScrapPost 승인 path 도 여기에 추가.
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import (
    AuditLog, Battle, BattleEvent, BattleParticipant, Infra, Scenario, ScrapPost, User,
)
from ..schemas import ScenarioOut, SmokeResult
from ..security import require_admin
from ..services import audit, auto_monitor, battle_service as bs, scenario_jobs
from ..services import cohort_service as cs
from ..services import assessor_client
from ..services.dry_run import review_scenario
from ..services.scrap_crawler import fetch_hn_top, seed_demo
from ..services.six_smoke import run_smoke

router = APIRouter(prefix="/admin", tags=["admin"])


class GenerateIn(BaseModel):
    request: str = Field(min_length=8, max_length=2000)
    course_ref: str | None = Field(default=None, max_length=120)   # e.g. "course3"
    weeks_spec: str | None = Field(default=None, max_length=80)    # e.g. "1-3"


class GenerateOut(BaseModel):
    job_id: str
    status: str


class JobOut(BaseModel):
    id: str
    status: str
    request: str
    course_ref: str | None
    weeks_spec: str | None
    queued_at: str
    started_at: str | None = None
    finished_at: str | None = None
    scenario_id: int | None = None
    preview: dict | None = None
    meta: dict | None = None
    error: str | None = None


class ActivateIn(BaseModel):
    activate: bool = True


@router.post("/scenarios/generate", response_model=GenerateOut, status_code=202)
async def generate(
    body: GenerateIn,
    request: Request,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> GenerateOut:
    jid = scenario_jobs.start_job(
        request=body.request,
        course_ref=body.course_ref,
        weeks_spec=body.weeks_spec,
        created_by=admin.id,
    )
    await audit.record(
        session, actor=admin, action="scenario.generate",
        target_type="job", target_id=jid,
        detail={"course_ref": body.course_ref, "weeks_spec": body.weeks_spec,
                "request_preview": body.request[:200]},
        request=request,
    )
    return GenerateOut(job_id=jid, status="queued")


@router.get("/scenarios/jobs", response_model=list[JobOut])
async def list_jobs(admin: User = Depends(require_admin)) -> list[JobOut]:
    return [JobOut(**j) for j in scenario_jobs.list_jobs()]


@router.get("/scenarios/jobs/{job_id}", response_model=JobOut)
async def get_job(job_id: str, admin: User = Depends(require_admin)) -> JobOut:
    j = scenario_jobs.get_job(job_id)
    if not j:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job not found")
    return JobOut(**j)


@router.post("/scenarios/{scenario_id}/dry-run")
async def trigger_dry_run(
    scenario_id: int,
    request: Request,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """수동 dry-run 트리거 — 자동 dry-run 이 실패했거나 시나리오 수정 후 재검증할 때."""
    s = await session.get(Scenario, scenario_id)
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "scenario not found")
    from ..models import Infra
    infra = (await session.scalars(select(Infra).limit(1))).first()
    scenario_dict = {
        "title": s.title, "description": s.description,
        "mission_red": s.mission_red, "mission_blue": s.mission_blue,
    }
    result = await review_scenario(scenario_dict, infra=infra)
    scoring = dict(s.scoring or {})
    scoring["dry_run"] = result
    s.scoring = scoring
    if result.get("passed"):
        s.status = "validated"
    await session.commit()
    await audit.record(
        session, actor=admin, action="scenario.dry_run",
        target_type="scenario", target_id=scenario_id,
        detail={"passed": bool(result.get("passed")),
                "pass_rate": result.get("pass_rate"),
                "promoted_to_validated": result.get("passed")},
        request=request,
    )
    return result


@router.post("/scenarios/{scenario_id}/activate", response_model=ScenarioOut)
async def activate_scenario(
    scenario_id: int,
    body: ActivateIn,
    request: Request,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ScenarioOut:
    s = await session.get(Scenario, scenario_id)
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "scenario not found")
    prev = s.status
    s.status = "validated" if body.activate else "draft"
    await session.commit()
    await session.refresh(s)
    await audit.record(
        session, actor=admin,
        action="scenario.activate" if body.activate else "scenario.deactivate",
        target_type="scenario", target_id=scenario_id,
        detail={"prev_status": prev, "new_status": s.status},
        request=request,
    )
    return ScenarioOut.model_validate(s)


class ScrapOut(BaseModel):
    id: int
    source: str
    source_url: str
    title: str
    summary: str
    relevance: dict
    status: str
    decided_at: str | None = None
    spawned_scenario_id: int | None = None
    created_at: str

    @classmethod
    def from_row(cls, r: ScrapPost) -> "ScrapOut":
        return cls(
            id=r.id, source=r.source, source_url=r.source_url,
            title=r.title, summary=r.summary, relevance=r.relevance or {},
            status=r.status,
            decided_at=r.decided_at.isoformat() if r.decided_at else None,
            spawned_scenario_id=r.spawned_scenario_id,
            created_at=r.created_at.isoformat() if r.created_at else "",
        )


@router.get("/scrap", response_model=list[ScrapOut])
async def list_scrap(
    status_filter: str | None = None,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> list[ScrapOut]:
    q = select(ScrapPost).order_by(ScrapPost.id.desc()).limit(100)
    if status_filter:
        q = q.where(ScrapPost.status == status_filter)
    rows = (await session.scalars(q)).all()
    return [ScrapOut.from_row(r) for r in rows]


@router.post("/scrap/seed")
async def scrap_seed(
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """데모 데이터 + (네트워크 가능 시) HN top 매칭 게시글 삽입."""
    n_demo = await seed_demo(session)
    n_hn = await fetch_hn_top(session, n=5)
    return {"inserted_demo": n_demo, "inserted_hn": n_hn}


class ScrapDecisionOut(BaseModel):
    scrap: ScrapOut
    job_id: str | None = None


@router.post("/scrap/{scrap_id}/approve", response_model=ScrapDecisionOut)
async def approve_scrap(
    scrap_id: int,
    request: Request,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ScrapDecisionOut:
    import datetime as _dt
    sp = await session.get(ScrapPost, scrap_id)
    if not sp:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "scrap not found")
    if sp.status != "pending":
        return ScrapDecisionOut(scrap=ScrapOut.from_row(sp), job_id=None)

    sp.status = "approved"
    sp.decided_by = admin.id
    sp.decided_at = _dt.datetime.now(_dt.timezone.utc)

    # KG match 가 있으면 첫 번째 항목을 course/weeks 로 분해
    course_ref: str | None = None
    weeks_spec: str | None = None
    matches = (sp.relevance or {}).get("kg_match") or []
    if matches:
        first = matches[0]
        # "course3-web-vuln/week04" 형태
        parts = first.split("/")
        if parts:
            course_ref = parts[0].split("-")[0]
        if len(parts) > 1:
            week_str = parts[1].replace("week", "").lstrip("0") or "1"
            weeks_spec = week_str

    request = (
        f"외부 위협 스크랩 기반 공방전: {sp.title}\n"
        f"요약: {sp.summary}\n"
        "이 위협을 6v6 인프라에서 재현·탐지·차단하는 Red/Blue 미션을 만들어줘."
    )
    job_id = scenario_jobs.start_job(
        request=request, course_ref=course_ref, weeks_spec=weeks_spec,
        created_by=admin.id, scrap_id=sp.id,
    )
    # job 완료 시 spawned_scenario_id 채우기는 background — 여기서는 일단 job_id 만 기록
    rel = dict(sp.relevance or {})
    rel["spawned_job_id"] = job_id
    sp.relevance = rel
    await session.commit()
    await session.refresh(sp)
    await audit.record(
        session, actor=admin, action="scrap.approve",
        target_type="scrap", target_id=scrap_id,
        detail={"job_id": job_id, "course_ref": course_ref, "weeks_spec": weeks_spec,
                "title": sp.title[:160]},
        request=request,
    )
    return ScrapDecisionOut(scrap=ScrapOut.from_row(sp), job_id=job_id)


@router.post("/scrap/{scrap_id}/reject", response_model=ScrapOut)
async def reject_scrap(
    scrap_id: int,
    request: Request,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ScrapOut:
    import datetime as _dt
    sp = await session.get(ScrapPost, scrap_id)
    if not sp:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "scrap not found")
    sp.status = "rejected"
    sp.decided_by = admin.id
    sp.decided_at = _dt.datetime.now(_dt.timezone.utc)
    await session.commit()
    await session.refresh(sp)
    await audit.record(
        session, actor=admin, action="scrap.reject",
        target_type="scrap", target_id=scrap_id,
        detail={"title": sp.title[:160]},
        request=request,
    )
    return ScrapOut.from_row(sp)


@router.get("/scenarios/drafts", response_model=list[ScenarioOut])
async def list_drafts(
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> list[ScenarioOut]:
    rows = (await session.scalars(
        select(Scenario).where(Scenario.status == "draft").order_by(Scenario.id.desc())
    )).all()
    return [ScenarioOut.model_validate(r) for r in rows]


# ── Phase 7: 관리자 대시보드 ──────────────────────
class StatsOut(BaseModel):
    user_count: int
    student_count: int
    admin_count: int
    scenario_total: int
    scenario_validated: int
    scenario_draft: int
    scrap_pending: int
    battles_total: int
    battles_active: int
    battles_completed: int
    events_total: int
    top_scorers: list[dict]


@router.get("/stats", response_model=StatsOut)
async def admin_stats(
    cohort_id: int | None = None,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> StatsOut:
    from sqlalchemy import func
    # cohort_id 지정 시 user/battle 통계를 해당 서브트리로 스코프. 미지정이면 전체.
    cohort_uids: set[int] | None = None
    cohort_bids: list[int] | None = None
    if cohort_id is not None:
        cohort_uids = await cs.user_ids_in_subtree(session, cohort_id)
        sub_ids = await cs.subtree_ids(session, cohort_id)
        brows = (await session.scalars(
            select(Battle.id).where(Battle.cohort_id.in_(sub_ids))
        )).all() if sub_ids else []
        cohort_bids = list(brows)

    def _scoped_user_q(base):
        if cohort_uids is not None:
            return base.where(User.id.in_(cohort_uids or {-1}))
        return base

    user_count = int((await session.execute(
        _scoped_user_q(select(func.count(User.id))))).scalar_one())
    student_count = int((await session.execute(
        _scoped_user_q(select(func.count(User.id)).where(User.role == "student"))
    )).scalar_one())
    admin_count = int((await session.execute(
        _scoped_user_q(select(func.count(User.id)).where(User.role == "admin"))
    )).scalar_one())

    scn_total = int((await session.execute(select(func.count(Scenario.id)))).scalar_one())
    scn_val = int((await session.execute(
        select(func.count(Scenario.id)).where(Scenario.status == "validated")
    )).scalar_one())
    scn_draft = int((await session.execute(
        select(func.count(Scenario.id)).where(Scenario.status == "draft")
    )).scalar_one())

    scrap_pending = int((await session.execute(
        select(func.count(ScrapPost.id)).where(ScrapPost.status == "pending")
    )).scalar_one())

    def _scoped_battle_q(base):
        if cohort_bids is not None:
            return base.where(Battle.id.in_(cohort_bids or [-1]))
        return base

    btl_total = int((await session.execute(
        _scoped_battle_q(select(func.count(Battle.id))))).scalar_one())
    btl_active = int((await session.execute(
        _scoped_battle_q(select(func.count(Battle.id)).where(Battle.status == "active"))
    )).scalar_one())
    btl_completed = int((await session.execute(
        _scoped_battle_q(select(func.count(Battle.id)).where(Battle.status == "completed"))
    )).scalar_one())

    ev_q = select(func.count(BattleEvent.id))
    if cohort_bids is not None:
        ev_q = ev_q.where(BattleEvent.battle_id.in_(cohort_bids or [-1]))
    ev_total = int((await session.execute(ev_q)).scalar_one())

    # top scorers — User × sum(BattleParticipant.score)
    top_q = (
        select(
            User.id, User.name,
            func.coalesce(func.sum(BattleParticipant.score), 0).label("total"),
        )
        .join(BattleParticipant, BattleParticipant.user_id == User.id, isouter=True)
        .group_by(User.id, User.name)
        .order_by(func.coalesce(func.sum(BattleParticipant.score), 0).desc())
        .limit(5)
    )
    if cohort_uids is not None:
        top_q = top_q.where(User.id.in_(cohort_uids or {-1}))
    top_rows = (await session.execute(top_q)).all()

    return StatsOut(
        user_count=user_count, student_count=student_count, admin_count=admin_count,
        scenario_total=scn_total, scenario_validated=scn_val, scenario_draft=scn_draft,
        scrap_pending=scrap_pending,
        battles_total=btl_total, battles_active=btl_active, battles_completed=btl_completed,
        events_total=ev_total,
        top_scorers=[
            {"user_id": r.id, "name": r.name, "total_score": int(r.total or 0)}
            for r in top_rows
        ],
    )


class AdminBattleOut(BaseModel):
    id: int
    scenario_id: int | None
    cohort_id: int | None = None
    scenario_title: str | None
    mode: str
    status: str
    monitor: str
    started_at: str | None
    ended_at: str | None
    time_limit_sec: int
    elapsed_sec: float
    participant_count: int
    event_count: int
    monitor_running: bool
    created_at: str


@router.get("/battles", response_model=list[AdminBattleOut])
async def admin_list_battles(
    status_filter: str | None = None,
    cohort_id: int | None = None,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> list[AdminBattleOut]:
    from sqlalchemy import func
    q = select(Battle).order_by(Battle.id.desc()).limit(200)
    if status_filter:
        q = q.where(Battle.status == status_filter)
    if cohort_id is not None:
        sub_ids = await cs.subtree_ids(session, cohort_id)
        q = q.where(Battle.cohort_id.in_(sub_ids or [-1]))
    battles = (await session.scalars(q)).all()

    out: list[AdminBattleOut] = []
    for b in battles:
        title = None
        if b.scenario_id:
            s = await session.get(Scenario, b.scenario_id)
            title = s.title if s else None
        pcount = int((await session.execute(
            select(func.count(BattleParticipant.id)).where(BattleParticipant.battle_id == b.id)
        )).scalar_one())
        ecount = int((await session.execute(
            select(func.count(BattleEvent.id)).where(BattleEvent.battle_id == b.id)
        )).scalar_one())
        elapsed, _ = bs.battle_elapsed(b)
        out.append(AdminBattleOut(
            id=b.id, scenario_id=b.scenario_id, cohort_id=b.cohort_id, scenario_title=title,
            mode=b.mode, status=b.status, monitor=b.monitor,
            started_at=b.started_at.isoformat() if b.started_at else None,
            ended_at=b.ended_at.isoformat() if b.ended_at else None,
            time_limit_sec=b.time_limit_sec,
            elapsed_sec=round(elapsed, 1),
            participant_count=pcount, event_count=ecount,
            monitor_running=auto_monitor.is_running(b.id),
            created_at=b.created_at.isoformat() if b.created_at else "",
        ))
    return out


@router.post("/battles/{battle_id}/monitor-tick")
async def trigger_monitor_tick(
    battle_id: int,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """auto-monitor 1 tick 을 즉시 실행 (Assessor 채점). 15s 폴링을 기다리지 않고
    채점을 강제하는 운영/e2e 용 컨트롤. 결정론 채점이므로 안전(부작용 0)."""
    from sqlalchemy import func
    b = await session.get(Battle, battle_id)
    if not b:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "battle not found")

    async def _count() -> int:
        return int((await session.execute(
            select(func.count(BattleEvent.id)).where(BattleEvent.battle_id == battle_id)
        )).scalar_one())

    before = await _count()
    await auto_monitor.run_once(battle_id)
    after = await _count()
    return {"battle_id": battle_id, "new_events": after - before}


@router.post("/battles/{battle_id}/force-end", response_model=AdminBattleOut)
async def force_end_battle(
    battle_id: int,
    request: Request,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> AdminBattleOut:
    try:
        b = await bs.cancel_battle(session, battle_id, actor_user_id=admin.id)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    auto_monitor.stop(battle_id)
    await audit.record(
        session, actor=admin, action="battle.force_end",
        target_type="battle", target_id=battle_id,
        detail={"final_status": b.status, "mode": b.mode},
        request=request,
    )
    return await _admin_battle_view(session, b)


@router.delete("/battles/{battle_id}", status_code=204)
async def admin_delete_battle(
    battle_id: int,
    request: Request,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> None:
    b = await session.get(Battle, battle_id)
    if not b:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "battle not found")
    auto_monitor.stop(battle_id)
    await session.delete(b)
    await session.commit()
    await audit.record(
        session, actor=admin, action="battle.delete",
        target_type="battle", target_id=battle_id,
        detail={"mode": b.mode, "prev_status": b.status},
        request=request,
    )


async def _admin_battle_view(session: AsyncSession, b: Battle) -> AdminBattleOut:
    from sqlalchemy import func
    title = None
    if b.scenario_id:
        s = await session.get(Scenario, b.scenario_id)
        title = s.title if s else None
    pcount = int((await session.execute(
        select(func.count(BattleParticipant.id)).where(BattleParticipant.battle_id == b.id)
    )).scalar_one())
    ecount = int((await session.execute(
        select(func.count(BattleEvent.id)).where(BattleEvent.battle_id == b.id)
    )).scalar_one())
    elapsed, _ = bs.battle_elapsed(b)
    return AdminBattleOut(
        id=b.id, scenario_id=b.scenario_id, cohort_id=b.cohort_id, scenario_title=title,
        mode=b.mode, status=b.status, monitor=b.monitor,
        started_at=b.started_at.isoformat() if b.started_at else None,
        ended_at=b.ended_at.isoformat() if b.ended_at else None,
        time_limit_sec=b.time_limit_sec,
        elapsed_sec=round(elapsed, 1),
        participant_count=pcount, event_count=ecount,
        monitor_running=auto_monitor.is_running(b.id),
        created_at=b.created_at.isoformat() if b.created_at else "",
    )


# ── 사용자 관리 ─────────────────────────────────────
class AdminUserOut(BaseModel):
    id: int
    email: str
    name: str
    role: str
    is_active: bool
    created_at: str


class UserPatchIn(BaseModel):
    role: str | None = Field(default=None, pattern=r"^(student|admin)$")
    is_active: bool | None = None


@router.get("/users", response_model=list[AdminUserOut])
async def admin_list_users(
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> list[AdminUserOut]:
    rows = (await session.scalars(select(User).order_by(User.id.asc()))).all()
    return [
        AdminUserOut(
            id=u.id, email=u.email, name=u.name, role=u.role, is_active=u.is_active,
            created_at=u.created_at.isoformat() if u.created_at else "",
        )
        for u in rows
    ]


@router.patch("/users/{user_id}", response_model=AdminUserOut)
async def admin_patch_user(
    user_id: int,
    body: UserPatchIn,
    request: Request,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> AdminUserOut:
    u = await session.get(User, user_id)
    if not u:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    if u.id == admin.id and (body.role == "student" or body.is_active is False):
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "cannot demote / deactivate yourself")
    prev = {"role": u.role, "is_active": u.is_active}
    if body.role is not None:
        u.role = body.role
    if body.is_active is not None:
        u.is_active = body.is_active
    await session.commit()
    await session.refresh(u)
    await audit.record(
        session, actor=admin, action="user.patch",
        target_type="user", target_id=user_id,
        detail={"prev": prev, "next": {"role": u.role, "is_active": u.is_active},
                "target_email": u.email},
        request=request,
    )
    return AdminUserOut(
        id=u.id, email=u.email, name=u.name, role=u.role, is_active=u.is_active,
        created_at=u.created_at.isoformat() if u.created_at else "",
    )


# ── 시나리오 archive / delete ───────────────────────
class ScenarioPatchIn(BaseModel):
    title: str | None = Field(default=None, min_length=4, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    time_limit_sec: int | None = Field(default=None, ge=300, le=7200)
    status: str | None = Field(default=None, pattern=r"^(draft|validated|active|archived)$")
    # 채점 AI 프로필 선택. 0 → 해제(기본 프로필 사용), >0 → 해당 프로필.
    grader_profile_id: int | None = Field(default=None, ge=0)


@router.patch("/scenarios/{scenario_id}", response_model=ScenarioOut)
async def admin_patch_scenario(
    scenario_id: int,
    body: ScenarioPatchIn,
    request: Request,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ScenarioOut:
    s = await session.get(Scenario, scenario_id)
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "scenario not found")
    prev = {"title": s.title, "status": s.status, "time_limit_sec": s.time_limit_sec}
    if body.title is not None:
        s.title = body.title
    if body.description is not None:
        s.description = body.description
    if body.time_limit_sec is not None:
        s.time_limit_sec = body.time_limit_sec
    if body.status is not None:
        s.status = body.status
    if body.grader_profile_id is not None:
        if body.grader_profile_id == 0:
            s.grader_profile_id = None       # 해제 → 기본 프로필 사용
        else:
            from ..models import GraderProfile
            if not await session.get(GraderProfile, body.grader_profile_id):
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "grader profile not found")
            s.grader_profile_id = body.grader_profile_id
    await session.commit()
    await session.refresh(s)
    await audit.record(
        session, actor=admin, action="scenario.patch",
        target_type="scenario", target_id=scenario_id,
        detail={"prev": prev,
                "next": {"title": s.title, "status": s.status,
                         "time_limit_sec": s.time_limit_sec,
                         "grader_profile_id": s.grader_profile_id}},
        request=request,
    )
    return ScenarioOut.model_validate(s)


# ── 감사 로그 ───────────────────────────────────────
class AuditOut(BaseModel):
    id: int
    actor_user_id: int | None
    actor_email: str | None
    action: str
    target_type: str | None
    target_id: str | None
    ip: str | None
    user_agent: str | None
    detail: dict
    ts: str


@router.get("/audit", response_model=list[AuditOut])
async def admin_list_audit(
    action_prefix: str | None = None,
    actor_user_id: int | None = None,
    target_type: str | None = None,
    limit: int = 100,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> list[AuditOut]:
    q = select(AuditLog).order_by(AuditLog.id.desc()).limit(min(max(limit, 1), 500))
    if action_prefix:
        q = q.where(AuditLog.action.like(f"{action_prefix}%"))
    if actor_user_id is not None:
        q = q.where(AuditLog.actor_user_id == actor_user_id)
    if target_type:
        q = q.where(AuditLog.target_type == target_type)
    rows = (await session.scalars(q)).all()
    return [
        AuditOut(
            id=r.id, actor_user_id=r.actor_user_id, actor_email=r.actor_email,
            action=r.action, target_type=r.target_type, target_id=r.target_id,
            ip=r.ip, user_agent=r.user_agent, detail=r.detail or {},
            ts=r.ts.isoformat() if r.ts else "",
        )
        for r in rows
    ]


@router.delete("/scenarios/{scenario_id}", status_code=204)
async def admin_delete_scenario(
    scenario_id: int,
    request: Request,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> None:
    s = await session.get(Scenario, scenario_id)
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "scenario not found")
    title = s.title
    await session.delete(s)
    await session.commit()
    await audit.record(
        session, actor=admin, action="scenario.delete",
        target_type="scenario", target_id=scenario_id,
        detail={"title": title},
        request=request,
    )


# ── 인프라 관리 (전체 학생 등록 인프라) ─────────────
class AdminInfraOut(BaseModel):
    id: int
    owner_id: int
    owner_name: str | None
    owner_email: str | None
    name: str
    vm_ip: str
    ssh_user: str
    bastion_api_key: str
    port_map: dict
    status: str
    last_smoke_at: str | None
    last_smoke_ok: bool | None
    created_at: str


async def _admin_infra_rows(session: AsyncSession, rows: list[Infra]) -> list[AdminInfraOut]:
    owners = {
        u.id: u for u in (await session.scalars(
            select(User).where(User.id.in_([r.owner_id for r in rows]))
        )).all()
    } if rows else {}
    out: list[AdminInfraOut] = []
    for r in rows:
        u = owners.get(r.owner_id)
        out.append(AdminInfraOut(
            id=r.id, owner_id=r.owner_id,
            owner_name=u.name if u else None, owner_email=u.email if u else None,
            name=r.name, vm_ip=r.vm_ip, ssh_user=r.ssh_user,
            bastion_api_key=r.bastion_api_key, port_map=r.port_map or {},
            status=r.status,
            last_smoke_at=r.last_smoke_at.isoformat() if r.last_smoke_at else None,
            last_smoke_ok=(r.last_smoke_result or {}).get("ok") if r.last_smoke_result else None,
            created_at=r.created_at.isoformat() if r.created_at else "",
        ))
    return out


@router.get("/infras", response_model=list[AdminInfraOut])
async def admin_list_infras(
    owner_id: int | None = None,
    status_filter: str | None = None,
    cohort_id: int | None = None,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> list[AdminInfraOut]:
    """전체 학생이 등록한 인프라 목록(소유자 정보 포함). owner/status/cohort 서브트리 필터."""
    q = select(Infra).order_by(Infra.id.desc()).limit(500)
    if owner_id is not None:
        q = q.where(Infra.owner_id == owner_id)
    if status_filter:
        q = q.where(Infra.status == status_filter)
    if cohort_id is not None:
        uids = await cs.user_ids_in_subtree(session, cohort_id)
        q = q.where(Infra.owner_id.in_(uids or {-1}))
    rows = (await session.scalars(q)).all()
    return await _admin_infra_rows(session, list(rows))


@router.post("/infras/{infra_id}/smoke", response_model=SmokeResult)
async def admin_infra_smoke(
    infra_id: int,
    request: Request,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> SmokeResult:
    """관리자가 임의 학생 인프라에 smoke 테스트 실행 + 상태 갱신."""
    import datetime as _dt
    infra = await session.get(Infra, infra_id)
    if not infra:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "infra not found")
    result = await run_smoke(ip=infra.vm_ip, bastion_api_key=infra.bastion_api_key,
                             port_map=infra.port_map or None)
    infra.last_smoke_at = _dt.datetime.now(_dt.timezone.utc)
    infra.last_smoke_result = result.model_dump()
    infra.status = "healthy" if result.ok else "degraded"
    await session.commit()
    await audit.record(
        session, actor=admin, action="infra.smoke",
        target_type="infra", target_id=infra_id,
        detail={"owner_id": infra.owner_id, "vm_ip": infra.vm_ip, "ok": result.ok},
        request=request,
    )
    return result


class AssessCheckOut(BaseModel):
    infra_id: int
    vm_ip: str
    assessor_ok: bool
    bastion_ok: bool
    evidence: str | None = None
    error: str | None = None


@router.post("/infras/{infra_id}/assess-check", response_model=AssessCheckOut)
async def admin_infra_assess_check(
    infra_id: int,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> AssessCheckOut:
    """채점 도달성 확인 — 학생 infra 의 Assessor `/assess`(읽기 전용 1건)·`/activity` 왕복 점검.
    '이 학생을 지금 채점할 수 있는가'를 관리자가 즉시 확인."""
    infra = await session.get(Infra, infra_id)
    if not infra:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "infra not found")
    resp = await assessor_client.assess(
        infra, [{"id": "ping", "type": "file_exists", "target": "web",
                 "params": {"path": "/etc/passwd"}}])
    act = await assessor_client.activity(infra, since_sec=60, want=["services"])
    ev = None
    if resp.get("results"):
        ev = resp["results"][0].get("evidence")
    return AssessCheckOut(
        infra_id=infra_id, vm_ip=infra.vm_ip,
        assessor_ok=bool(resp.get("ok")),
        bastion_ok=bool(act.get("ok")),
        evidence=ev, error=resp.get("error"),
    )


@router.delete("/infras/{infra_id}", status_code=204)
async def admin_delete_infra(
    infra_id: int,
    request: Request,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> None:
    infra = await session.get(Infra, infra_id)
    if not infra:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "infra not found")
    meta = {"owner_id": infra.owner_id, "vm_ip": infra.vm_ip, "name": infra.name}
    await session.delete(infra)
    await session.commit()
    await audit.record(
        session, actor=admin, action="infra.delete",
        target_type="infra", target_id=infra_id, detail=meta, request=request,
    )
