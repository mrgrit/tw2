"""(옵션) 플랫폼 룰 무장 — 미션 `arm_rule` 템플릿을 6v6 `/provision-rule` 로 적용/회수.

**기본 OFF**(`SKIP_PROVISIONER` 기본 skip). 기본 채점 경로는 check-spec 온디맨드이며
룰 무장은 불필요하다. 학생 작성 룰 미션은 `check_compiler` 가 file_contains+wazuh_alert 로
채점하므로 무장이 필요 없다.

활성화: env `SKIP_PROVISIONER=0` (또는 false/no). 활성 시 battle 시작에 arm, 종료에 withdraw.
검증된 템플릿만 무장 — `arm_rule` 은 시나리오에 선언된 파라미터 템플릿(LLM free-form 금지).
"""
from __future__ import annotations
import logging
import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Battle, BattleParticipant, Infra, Scenario
from . import assessor_client, battlefield

log = logging.getLogger(__name__)


def is_skipped() -> bool:
    """기본 OFF: SKIP_PROVISIONER 미설정/참 → skip. '0'/'false'/'no' 일 때만 활성."""
    return os.getenv("SKIP_PROVISIONER", "1").lower() not in ("0", "false", "no")


async def _role_infra(session: AsyncSession, battle_id: int) -> dict[str, Infra]:
    parts = (await session.scalars(
        select(BattleParticipant).where(BattleParticipant.battle_id == battle_id)
    )).all()
    role_infra: dict[str, Infra] = {}
    for p in parts:
        inf = await session.get(Infra, p.infra_id) if p.infra_id else None
        if not inf:
            continue
        if p.role in ("red", "blue"):
            role_infra[p.role] = inf
        elif p.role in ("solo", "free"):
            role_infra.setdefault("red", inf)
            role_infra.setdefault("blue", inf)
    return role_infra


async def _apply(session: AsyncSession, battle_id: int, action: str) -> dict:
    if is_skipped():
        return {"skipped": True, "action": action, "count": 0}
    battle = await session.get(Battle, battle_id)
    if not battle or not battle.scenario_id:
        return {"skipped": False, "action": action, "count": 0}
    scenario = await session.get(Scenario, battle.scenario_id)
    role_infra = await _role_infra(session, battle_id)
    count = 0
    for side in ("red", "blue"):
        missions = ((scenario.mission_red if side == "red" else scenario.mission_blue) or {}).get("missions") or []
        for m in missions:
            rule = m.get("arm_rule")
            if not rule:
                continue
            target = battlefield.resolve_target_infra(
                side, battlefield.normalize_assess_target(m.get("assess_target")), role_infra)
            if not target:
                continue
            resp = await assessor_client.provision_rule(target, action=action, rule=rule,
                                                        battle_id=battle_id)
            if resp.get("ok"):
                count += 1
            else:
                log.warning("provision %s mission rule failed: %s", action, resp.get("error"))
    return {"skipped": False, "action": action, "count": count}


async def arm_battle_rules(session: AsyncSession, battle_id: int) -> dict:
    return await _apply(session, battle_id, "arm")


async def withdraw_battle_rules(session: AsyncSession, battle_id: int) -> dict:
    return await _apply(session, battle_id, "withdraw")
