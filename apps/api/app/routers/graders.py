"""채점 AI 프로필 관리 — 등록/수정/목록/삭제/기본설정 (admin 전용).

provider: cc(Claude Code) | bastion(6v6 LLM). 시나리오별로 선택해 채점 AI/모델을 지정.
api_key 는 응답에 노출하지 않는다(has_api_key 만).
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import GraderProfile, User
from ..schemas import GraderProfileIn, GraderProfileOut, GraderProfilePatchIn
from ..security import require_admin
from ..services import audit

router = APIRouter(prefix="/admin/graders", tags=["graders"])


def _out(p: GraderProfile) -> GraderProfileOut:
    return GraderProfileOut(
        id=p.id, name=p.name, provider=p.provider, model=p.model, base_url=p.base_url,
        has_api_key=bool(p.api_key), enabled=p.enabled, is_default=p.is_default,
        created_at=p.created_at,
    )


async def _clear_other_defaults(session: AsyncSession, keep_id: int | None) -> None:
    q = update(GraderProfile).values(is_default=False)
    if keep_id is not None:
        q = q.where(GraderProfile.id != keep_id)
    await session.execute(q)


@router.get("", response_model=list[GraderProfileOut])
async def list_graders(
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> list[GraderProfileOut]:
    rows = (await session.scalars(select(GraderProfile).order_by(GraderProfile.id.asc()))).all()
    return [_out(p) for p in rows]


@router.post("", response_model=GraderProfileOut, status_code=201)
async def create_grader(
    body: GraderProfileIn,
    request: Request,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> GraderProfileOut:
    if body.provider == "bastion" and not body.base_url:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "bastion provider requires base_url")
    if await session.scalar(select(GraderProfile).where(GraderProfile.name == body.name)):
        raise HTTPException(status.HTTP_409_CONFLICT, "grader name already exists")
    p = GraderProfile(
        name=body.name, provider=body.provider, model=body.model, base_url=body.base_url,
        api_key=body.api_key, enabled=body.enabled, is_default=body.is_default,
    )
    session.add(p)
    await session.flush()
    if body.is_default:
        await _clear_other_defaults(session, keep_id=p.id)
    await session.commit()
    await session.refresh(p)
    await audit.record(session, actor=admin, action="grader.create",
                       target_type="grader", target_id=p.id,
                       detail={"name": p.name, "provider": p.provider, "model": p.model},
                       request=request)
    return _out(p)


@router.patch("/{grader_id}", response_model=GraderProfileOut)
async def patch_grader(
    grader_id: int,
    body: GraderProfilePatchIn,
    request: Request,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> GraderProfileOut:
    p = await session.get(GraderProfile, grader_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "grader not found")
    fields = body.model_dump(exclude_unset=True)
    for k in ("name", "provider", "model", "base_url", "api_key", "enabled", "is_default"):
        if k in fields:
            setattr(p, k, fields[k])
    if (p.provider == "bastion") and not p.base_url:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "bastion provider requires base_url")
    await session.flush()
    if fields.get("is_default"):
        await _clear_other_defaults(session, keep_id=p.id)
    await session.commit()
    await session.refresh(p)
    await audit.record(session, actor=admin, action="grader.patch",
                       target_type="grader", target_id=grader_id,
                       detail={"changed": list(fields.keys())}, request=request)
    return _out(p)


@router.delete("/{grader_id}", status_code=204)
async def delete_grader(
    grader_id: int,
    request: Request,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> None:
    p = await session.get(GraderProfile, grader_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "grader not found")
    name = p.name
    await session.delete(p)  # Scenario.grader_profile_id → SET NULL
    await session.commit()
    await audit.record(session, actor=admin, action="grader.delete",
                       target_type="grader", target_id=grader_id,
                       detail={"name": name}, request=request)
