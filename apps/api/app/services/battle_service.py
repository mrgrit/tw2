"""DB-backed battle 상태 관리.

Phase 1 의 in-memory `_battles` dict (CCC battle_engine) 를 대체. SQLAlchemy 트랜잭션
하나로 Battle + BattleParticipant + BattleEvent 를 갱신한다. EventType 표는
`packages/battle_engine` 의 enum 을 그대로 재사용.
"""
from __future__ import annotations
import datetime as dt
from typing import Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models import Battle, BattleEvent, BattleParticipant, Infra, Scenario, User


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _aware(d: dt.datetime | None) -> dt.datetime | None:
    """sqlite 등은 DateTime(timezone=True) 컬럼이어도 naive 로 돌려준다 — UTC 로 정규화."""
    if d is None:
        return None
    if d.tzinfo is None:
        return d.replace(tzinfo=dt.timezone.utc)
    return d


# ── 모드 검증 ────────────────────────────────────────
def validate_participants(mode: str, participants: list[dict]) -> None:
    if not participants:
        raise ValueError("at least one participant required")
    roles = [p["role"] for p in participants]
    user_ids = [p["user_id"] for p in participants]

    if len(set(user_ids)) != len(user_ids):
        raise ValueError("duplicate user_id in participants")

    if mode == "solo":
        if len(participants) != 1:
            raise ValueError("solo mode requires exactly 1 participant")
        if roles[0] != "solo":
            raise ValueError("solo mode participant must have role='solo'")
    elif mode == "duel":
        if len(participants) != 2:
            raise ValueError("duel mode requires exactly 2 participants")
        if sorted(roles) != ["blue", "red"]:
            raise ValueError("duel mode requires one 'red' and one 'blue'")
    elif mode == "ffa":
        if len(participants) < 2:
            raise ValueError("ffa mode requires at least 2 participants")
        if any(r not in ("free", "red", "blue") for r in roles):
            raise ValueError("ffa mode roles must be 'free' (or red/blue if mixed)")
    else:
        raise ValueError(f"unknown mode: {mode}")


# ── 생성 / 조회 / 시작 / 종료 ─────────────────────────
async def create_battle(
    session: AsyncSession,
    *,
    scenario_id: int,
    mode: str,
    monitor: str,
    participants: list[dict],
    created_by: int,
) -> Battle:
    validate_participants(mode, participants)

    scenario = await session.get(Scenario, scenario_id)
    if not scenario:
        raise ValueError(f"scenario {scenario_id} not found")
    if scenario.status not in ("validated", "active"):
        raise ValueError(f"scenario {scenario_id} is {scenario.status}, not playable")

    # 참가자의 user / infra 존재 검증
    for p in participants:
        u = await session.get(User, p["user_id"])
        if not u:
            raise ValueError(f"user {p['user_id']} not found")
        if p.get("infra_id") is not None:
            inf = await session.get(Infra, p["infra_id"])
            if not inf or inf.owner_id != p["user_id"]:
                raise ValueError(f"infra {p['infra_id']} not owned by user {p['user_id']}")

    battle = Battle(
        scenario_id=scenario_id,
        mode=mode,
        monitor=monitor,
        time_limit_sec=int(scenario.time_limit_sec),
        status="pending",
        created_by=created_by,
    )
    session.add(battle)
    await session.flush()

    for p in participants:
        session.add(BattleParticipant(
            battle_id=battle.id,
            user_id=p["user_id"],
            infra_id=p.get("infra_id"),
            role=p["role"],
            score=0,
        ))

    session.add(BattleEvent(
        battle_id=battle.id,
        actor_user_id=created_by,
        event_type="system",
        target="",
        description=f"battle created (mode={mode}, scenario={scenario_id})",
        points=0,
    ))
    await session.commit()
    return await load_battle(session, battle.id)


async def load_battle(session: AsyncSession, battle_id: int) -> Battle:
    stmt = (
        select(Battle)
        .options(selectinload(Battle.participants), selectinload(Battle.events))
        .where(Battle.id == battle_id)
    )
    b = await session.scalar(stmt)
    if not b:
        raise ValueError(f"battle {battle_id} not found")
    return b


async def is_participant(session: AsyncSession, battle_id: int, user_id: int) -> bool:
    row = await session.scalar(
        select(BattleParticipant.id).where(
            BattleParticipant.battle_id == battle_id,
            BattleParticipant.user_id == user_id,
        )
    )
    return row is not None


async def start_battle(session: AsyncSession, battle_id: int, actor_user_id: int) -> Battle:
    b = await session.get(Battle, battle_id)
    if not b:
        raise ValueError(f"battle {battle_id} not found")
    if b.status != "pending":
        raise ValueError(f"battle {battle_id} already {b.status}")
    b.status = "active"
    b.started_at = _now()

    session.add(BattleEvent(
        battle_id=b.id,
        actor_user_id=actor_user_id,
        event_type="system",
        description="battle started",
        points=0,
    ))
    await session.commit()
    return await load_battle(session, battle_id)


async def add_event(
    session: AsyncSession,
    *,
    battle_id: int,
    actor_user_id: int,
    event_type: str,
    target: str,
    description: str,
    points: int,
    detail: dict,
) -> BattleEvent:
    """이벤트 추가 + actor 점수 반영 + 시간 만료 시 자동 종료."""
    b = await session.get(Battle, battle_id)
    if not b:
        raise ValueError(f"battle {battle_id} not found")
    if b.status not in ("active",):
        raise ValueError(f"battle {battle_id} is {b.status}, not active")

    ev = BattleEvent(
        battle_id=b.id,
        actor_user_id=actor_user_id,
        event_type=event_type,
        target=target,
        description=description,
        detail=detail or {},
        points=points,
    )
    session.add(ev)

    if points:
        part = await session.scalar(
            select(BattleParticipant).where(
                BattleParticipant.battle_id == b.id,
                BattleParticipant.user_id == actor_user_id,
            )
        )
        if part:
            part.score = (part.score or 0) + points

    started = _aware(b.started_at)
    if started and b.time_limit_sec > 0:
        elapsed = (_now() - started).total_seconds()
        if elapsed >= b.time_limit_sec:
            b.status = "completed"
            b.ended_at = _now()
            session.add(BattleEvent(
                battle_id=b.id,
                actor_user_id=None,
                event_type="system",
                description="time expired",
                points=0,
            ))

    await session.commit()
    await session.refresh(ev)
    return ev


async def end_battle(session: AsyncSession, battle_id: int, actor_user_id: int) -> Battle:
    b = await session.get(Battle, battle_id)
    if not b:
        raise ValueError(f"battle {battle_id} not found")
    if b.status in ("completed", "cancelled"):
        return await load_battle(session, battle_id)
    b.status = "completed"
    b.ended_at = _now()

    parts = (await session.scalars(
        select(BattleParticipant).where(BattleParticipant.battle_id == b.id)
    )).all()
    summary = {p.role: p.score for p in parts}
    session.add(BattleEvent(
        battle_id=b.id,
        actor_user_id=actor_user_id,
        event_type="system",
        description="battle ended (manual)",
        detail={"final_scores": summary},
    ))
    await session.commit()
    return await load_battle(session, battle_id)


async def cancel_battle(session: AsyncSession, battle_id: int, actor_user_id: int) -> Battle:
    b = await session.get(Battle, battle_id)
    if not b:
        raise ValueError(f"battle {battle_id} not found")
    if b.status in ("completed", "cancelled"):
        return await load_battle(session, battle_id)
    b.status = "cancelled"
    b.ended_at = _now()
    session.add(BattleEvent(
        battle_id=b.id,
        actor_user_id=actor_user_id,
        event_type="system",
        description="battle cancelled (admin)",
    ))
    await session.commit()
    return await load_battle(session, battle_id)


def battle_elapsed(b: Battle) -> tuple[float, float]:
    started = _aware(b.started_at)
    if not started:
        return (0.0, float(b.time_limit_sec))
    end = _aware(b.ended_at) or _now()
    elapsed = (end - started).total_seconds()
    remaining = max(0.0, b.time_limit_sec - elapsed)
    return (elapsed, remaining)
