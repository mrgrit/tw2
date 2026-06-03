"""실습 모니터링 라우터 — 진도 대시보드, 활동 타임라인, lab-tick, 중앙 SIEM 딥링크.

채점(battles)과 별개 트랙. 진도/병목 산출은 결정론(LLM 0), 피드백 작성만 CC.
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import ActivityEvent, Battle, User
from ..schemas import ActivityEventOut, CohortProgressOut, StudentProgressOut
from ..security import get_current_user, require_admin
from ..services import lab_monitor, siem_export
from ..services import cohort_service as cs
from ..services import feedback as fb_svc

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
