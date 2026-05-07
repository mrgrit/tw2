"""관리자 전용 라우터 — Claude Code 시나리오 생성, 시나리오 활성화, 강제 종료 등.

권한: 모든 엔드포인트 require_admin. Phase 5 에서 ScrapPost 승인 path 도 여기에 추가.
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Scenario, User
from ..schemas import ScenarioOut
from ..security import require_admin
from ..services import scenario_jobs

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


@router.get("/scenarios/drafts", response_model=list[ScenarioOut])
async def list_drafts(
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> list[ScenarioOut]:
    rows = (await session.scalars(
        select(Scenario).where(Scenario.status == "draft").order_by(Scenario.id.desc())
    )).all()
    return [ScenarioOut.model_validate(r) for r in rows]
