"""6v6 인프라 등록 / 조회 / smoke 테스트.

학생 1인 = 1세트 6v6 VM (외부 IP 1개 + 포트 80/443/2204/2202/8000/5601/9100).
"""
from __future__ import annotations
import asyncio
import socket
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..crypto import encrypt
from ..db import get_session
from ..models import Infra, User
from ..schemas import InfraIn, InfraOut, SmokeResult
from ..security import get_current_user
from ..services.six_smoke import run_smoke

router = APIRouter(prefix="/infras", tags=["infras"])


@router.get("", response_model=list[InfraOut])
async def list_my(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)) -> list[InfraOut]:
    rows = (await session.scalars(select(Infra).where(Infra.owner_id == user.id).order_by(Infra.id.desc()))).all()
    return [InfraOut.model_validate(r) for r in rows]


@router.post("", response_model=InfraOut)
async def create(body: InfraIn, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)) -> InfraOut:
    # 학생 1인 = 인프라 1개 (Phase 1 단순화)
    existing = await session.scalar(select(Infra).where(Infra.owner_id == user.id))
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "infra already registered. delete first or PATCH.")

    infra = Infra(
        owner_id=user.id,
        name=body.name,
        vm_ip=body.vm_ip,
        ssh_user=body.ssh_user,
        ssh_password_enc=encrypt(body.ssh_password),
        bastion_api_key=body.bastion_api_key,
        status="registered",
    )
    session.add(infra)
    await session.commit()
    await session.refresh(infra)
    return InfraOut.model_validate(infra)


@router.delete("/{infra_id}", status_code=204)
async def delete(infra_id: int, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)) -> None:
    infra = await session.get(Infra, infra_id)
    if not infra or (infra.owner_id != user.id and user.role != "admin"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "infra not found")
    await session.delete(infra)
    await session.commit()


@router.post("/{infra_id}/smoke", response_model=SmokeResult)
async def smoke(infra_id: int, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)) -> SmokeResult:
    infra = await session.get(Infra, infra_id)
    if not infra or (infra.owner_id != user.id and user.role != "admin"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "infra not found")

    result = await run_smoke(
        ip=infra.vm_ip,
        bastion_api_key=infra.bastion_api_key,
    )

    import datetime as dt
    infra.last_smoke_at = dt.datetime.now(dt.timezone.utc)
    infra.last_smoke_result = result.model_dump()
    infra.status = "healthy" if result.ok else "degraded"
    await session.commit()
    return result
