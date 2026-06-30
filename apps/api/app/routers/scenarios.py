"""시나리오 카탈로그 — 학생/관리자 모두 read 가능, 작성/수정은 admin."""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Scenario, User
from ..schemas import ScenarioOut
from ..security import get_current_user
from ..services import infra_render

router = APIRouter(prefix="/scenarios", tags=["scenarios"])


@router.get("", response_model=list[ScenarioOut])
async def list_scenarios(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[ScenarioOut]:
    rows = (
        await session.scalars(
            select(Scenario)
            .where(Scenario.status.in_(("validated", "active")))
            .order_by(Scenario.id.asc())
        )
    ).all()
    return [ScenarioOut.model_validate(r) for r in rows]


@router.get("/{scenario_id}")
async def get_scenario(
    scenario_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    s = await session.get(Scenario, scenario_id)
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "scenario not found")
    # 미션 텍스트의 {{TARGET_IP}}/{{WEB_ENTRY}}/{{ATTACKER_IP}} 를 요청자가 등록한 인프라로 치환.
    v = await infra_render.vars_for_user(session, user.id)
    base = ScenarioOut.model_validate(s).model_dump()
    base["description"] = infra_render.render(base.get("description"), v)
    return {
        **base,
        "course_ref": s.course_ref,
        "mission_red": infra_render.render(s.mission_red, v),
        "mission_blue": infra_render.render(s.mission_blue, v),
        "scoring": s.scoring,
    }
