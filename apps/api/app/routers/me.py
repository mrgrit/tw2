"""학생 셀프서비스 — 내 제출 저널(포트폴리오/복습) + 워크북 다운로드.

채점(battles)·강사 모니터링(monitoring)과 별개로, 학생이 *자기가 한 일* 을 시간순으로
복습하는 개인 학습 표면. `student_submissions` 가 단일 원천이며, battle/scenario 가 지워져도
이 기록은 남는다. 여기에 워크북(docx) export(Phase 4)도 얹는다.
"""
from __future__ import annotations
import io

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Scenario, StudentSubmission, User
from ..schemas import StudentSubmissionOut
from ..security import get_current_user
from ..services import workbook as wb

router = APIRouter(prefix="/me", tags=["me"])

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@router.get("/submissions", response_model=list[StudentSubmissionOut])
async def my_submissions(
    scenario_id: int | None = None,
    battle_id: int | None = None,
    limit: int = 500,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[StudentSubmissionOut]:
    """내 제출 히스토리(최신순) — 명령·결과·분석 + AI 피드백/점수.

    명령을 다시 내리지 않고도 자기가 한 일을 그대로 복습할 수 있는 포트폴리오.
    scenario_id/battle_id 로 좁힐 수 있다. 본인 것만 보인다(user_id 강제 스코프).
    """
    q = select(StudentSubmission).where(StudentSubmission.user_id == user.id)
    if scenario_id is not None:
        q = q.where(StudentSubmission.scenario_id == scenario_id)
    if battle_id is not None:
        q = q.where(StudentSubmission.battle_id == battle_id)
    q = q.order_by(StudentSubmission.id.desc()).limit(min(max(limit, 1), 1000))
    rows = (await session.scalars(q)).all()
    return [StudentSubmissionOut.model_validate(r) for r in rows]


@router.get("/workbook/{scenario_id}")
async def my_workbook(
    scenario_id: int,
    battle_id: int | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """내 제출로 **채워진 워크북(.docx)** 다운로드 — 미션 칸에 내가 입력한 명령·결과·분석 +
    AI 채점 결과가 자동으로 들어간 복습/제출용 초안.

    - 시나리오가 살아있으면 그 구조로, 삭제됐으면 내 제출 스냅샷으로 골격을 복원한다.
    - 제출이 없으면 빈 워크북(사전 배포본)을 그대로 받는다.
    - 본인 제출만 채워진다(user 스코프).
    """
    q = select(StudentSubmission).where(
        StudentSubmission.user_id == user.id,
        StudentSubmission.scenario_id == scenario_id)
    if battle_id is not None:
        q = q.where(StudentSubmission.battle_id == battle_id)
    subs = (await session.scalars(q.order_by(StudentSubmission.id))).all()

    scenario = await session.get(Scenario, scenario_id)
    if scenario is not None:
        scn_dict = wb.scenario_to_dict(scenario, student_name=user.name)
    elif subs:
        scn_dict = wb.dict_from_snapshots(list(subs), student_name=user.name)
    else:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no scenario and no submissions to build a workbook")

    doc = wb.build_doc(scn_dict, prefill=wb.prefill_from_submissions(list(subs)))
    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf, media_type=_DOCX_MIME,
        headers={"Content-Disposition": f'attachment; filename="workbook-{scenario_id}.docx"'})
