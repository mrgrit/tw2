"""학생별 피드백 라우터.

- 학생: 본인에게 전달된 피드백 열람(`GET /feedback/me`).
- 강사/admin: 생성(on-demand) · 검토 · 재생성.
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import StudentFeedback, User
from ..schemas import FeedbackCreateIn, StudentFeedbackOut
from ..security import get_current_user, require_admin
from ..services import feedback as fb_svc

router = APIRouter(prefix="/feedback", tags=["feedback"])


def _out(row: StudentFeedback) -> StudentFeedbackOut:
    return StudentFeedbackOut(
        id=row.id, user_id=row.user_id, cohort_id=row.cohort_id, battle_id=row.battle_id,
        scope=row.scope, trigger=row.trigger, content_md=row.content_md, basis=row.basis or {},
        model=row.model, cost_usd=round((row.cost_usd or 0) / 1_000_000, 6),
        delivered_to=row.delivered_to, created_at=row.created_at,
    )


@router.get("/me", response_model=list[StudentFeedbackOut])
async def my_feedback(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[StudentFeedbackOut]:
    rows = (await session.scalars(
        select(StudentFeedback).where(
            StudentFeedback.user_id == user.id,
            StudentFeedback.delivered_to.in_(["student", "both"]),
        ).order_by(StudentFeedback.id.desc())
    )).all()
    return [_out(r) for r in rows]


@router.get("", response_model=list[StudentFeedbackOut])
async def list_feedback(
    user_id: int | None = None,
    cohort_id: int | None = None,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> list[StudentFeedbackOut]:
    q = select(StudentFeedback).order_by(StudentFeedback.id.desc()).limit(200)
    if user_id is not None:
        q = q.where(StudentFeedback.user_id == user_id)
    if cohort_id is not None:
        q = q.where(StudentFeedback.cohort_id == cohort_id)
    rows = (await session.scalars(q)).all()
    return [_out(r) for r in rows]


@router.post("/students/{target_user_id}", response_model=StudentFeedbackOut, status_code=201)
async def create_feedback(
    target_user_id: int,
    body: FeedbackCreateIn,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> StudentFeedbackOut:
    """강사 on-demand 피드백 생성 (트리거=manual)."""
    try:
        fb = await fb_svc.generate_feedback(
            session, user_id=target_user_id, battle_id=body.battle_id,
            cohort_id=body.cohort_id, scope=body.scope, trigger="manual",
            delivered_to=body.delivered_to, note=body.note, created_by=admin.id,
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    return _out(fb)


@router.post("/students/{target_user_id}/integrate", response_model=StudentFeedbackOut, status_code=201)
async def integrate_feedback(
    target_user_id: int,
    cohort_id: int | None = None,
    battle_id: int | None = None,
    use_ai: bool = True,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> StudentFeedbackOut:
    """건건(lab) 피드백 + 통계 + 추천 직무 → **통합 피드백**(scope=periodic) 생성."""
    try:
        fb = await fb_svc.integrate_feedback(
            session, user_id=target_user_id, cohort_id=cohort_id,
            battle_id=battle_id, created_by=admin.id, use_ai=use_ai)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    return _out(fb)


@router.post("/{feedback_id}/regenerate", response_model=StudentFeedbackOut, status_code=201)
async def regenerate_feedback(
    feedback_id: int,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> StudentFeedbackOut:
    old = await session.get(StudentFeedback, feedback_id)
    if not old:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "feedback not found")
    fb = await fb_svc.generate_feedback(
        session, user_id=old.user_id, battle_id=old.battle_id, cohort_id=old.cohort_id,
        scope=old.scope, trigger="manual", delivered_to=old.delivered_to, created_by=admin.id,
    )
    return _out(fb)
