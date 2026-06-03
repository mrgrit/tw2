"""채점 AI 프로필 해석 — 시나리오별 등록/선택된 채점기를 결정.

우선순위: scenario.grader_profile_id → (없으면) is_default 프로필 → (없으면) CC fallback.
반환은 grade() 가 바로 쓰는 dict: {provider, model, base_url, api_key, profile_id, name}.
"""
from __future__ import annotations
import os
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import GraderProfile, Scenario

# CC 기본 모델 (프로필 없을 때 fallback)
_CC_DEFAULT_MODEL = os.getenv("TUBEWAR_ANALYZER_MODEL", "claude-haiku-4-5")


def _profile_dict(p: GraderProfile) -> dict:
    return {"provider": p.provider, "model": p.model, "base_url": p.base_url,
            "api_key": p.api_key, "profile_id": p.id, "name": p.name}


def _cc_fallback() -> dict:
    return {"provider": "cc", "model": _CC_DEFAULT_MODEL, "base_url": None,
            "api_key": None, "profile_id": None, "name": "CC (기본)"}


async def resolve_for_scenario(session: AsyncSession, scenario: Scenario | None) -> dict:
    if scenario is not None and scenario.grader_profile_id:
        p = await session.get(GraderProfile, scenario.grader_profile_id)
        if p and p.enabled:
            return _profile_dict(p)
    # 기본 프로필
    p = await session.scalar(
        select(GraderProfile).where(GraderProfile.is_default.is_(True),
                                    GraderProfile.enabled.is_(True)).limit(1)
    )
    if p:
        return _profile_dict(p)
    return _cc_fallback()
