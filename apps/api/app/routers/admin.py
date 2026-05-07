"""관리자 전용 라우터 — Claude Code 시나리오 생성, 시나리오 활성화, 강제 종료 등.

권한: 모든 엔드포인트 require_admin. Phase 5 에서 ScrapPost 승인 path 도 여기에 추가.
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Scenario, ScrapPost, User
from ..schemas import ScenarioOut
from ..security import require_admin
from ..services import scenario_jobs
from ..services.dry_run import review_scenario
from ..services.scrap_crawler import fetch_hn_top, seed_demo

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
async def generate(body: GenerateIn, admin: User = Depends(require_admin)) -> GenerateOut:
    jid = scenario_jobs.start_job(
        request=body.request,
        course_ref=body.course_ref,
        weeks_spec=body.weeks_spec,
        created_by=admin.id,
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
    return result


@router.post("/scenarios/{scenario_id}/activate", response_model=ScenarioOut)
async def activate_scenario(
    scenario_id: int,
    body: ActivateIn,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ScenarioOut:
    s = await session.get(Scenario, scenario_id)
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "scenario not found")
    s.status = "validated" if body.activate else "draft"
    await session.commit()
    await session.refresh(s)
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
    return ScrapDecisionOut(scrap=ScrapOut.from_row(sp), job_id=job_id)


@router.post("/scrap/{scrap_id}/reject", response_model=ScrapOut)
async def reject_scrap(
    scrap_id: int,
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
