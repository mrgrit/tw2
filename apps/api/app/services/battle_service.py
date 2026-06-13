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

from ..models import Battle, BattleEvent, BattleParticipant, Cohort, Infra, Scenario, User


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
def validate_participants(mode: str, participants: list[dict],
                          *, allow_lobby: bool = False) -> None:
    """admin 이 lobby (참가자 0명) 로 만들 수 있도록 allow_lobby 추가."""
    if not participants:
        if allow_lobby:
            return  # 로비 — 학생이 join 으로 채움
        raise ValueError("at least one participant required (or use lobby mode for admin)")
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
        if len(participants) > 2:
            raise ValueError("duel mode allows max 2 participants")
        for r in roles:
            if r not in ("red", "blue"):
                raise ValueError("duel mode roles must be 'red' or 'blue'")
        if len(roles) != len(set(roles)):
            raise ValueError("duel mode: each role (red/blue) only once")
    elif mode == "ffa":
        if any(r not in ("free", "red", "blue") for r in roles):
            raise ValueError("ffa mode roles must be 'free' (or red/blue if mixed)")
    else:
        raise ValueError(f"unknown mode: {mode}")


def validate_can_start(mode: str, participants: list[dict]) -> None:
    """start 시점에 mode 별 최소 인원 충족 검증."""
    if not participants:
        raise ValueError("battle has no participants — cannot start")
    if mode == "solo" and len(participants) != 1:
        raise ValueError("solo mode requires exactly 1 participant to start")
    if mode == "duel" and len(participants) != 2:
        raise ValueError("duel mode requires 2 participants (red+blue) to start")
    if mode == "ffa" and len(participants) < 2:
        raise ValueError("ffa mode requires at least 2 participants to start")


# ── 생성 / 조회 / 시작 / 종료 ─────────────────────────
VALID_TARGET_APPS = {
    "juiceshop", "dvwa", "neobank", "mediforum",
    "govportal", "aicompanion", "adminconsole", "web",
}


async def create_battle(
    session: AsyncSession,
    *,
    scenario_id: int,
    mode: str,
    monitor: str,
    participants: list[dict],
    created_by: int,
    target_apps: list[str] | None = None,
    hint_enabled: bool = False,
    allow_lobby: bool = False,
    cohort_id: int | None = None,
) -> Battle:
    validate_participants(mode, participants, allow_lobby=allow_lobby)

    scenario = await session.get(Scenario, scenario_id)
    if not scenario:
        raise ValueError(f"scenario {scenario_id} not found")
    if scenario.status not in ("validated", "active"):
        raise ValueError(f"scenario {scenario_id} is {scenario.status}, not playable")

    # cohort 지정(수업용)이면 존재 검증. None 이면 신원-only 모드.
    if cohort_id is not None:
        if not await session.get(Cohort, cohort_id):
            raise ValueError(f"cohort {cohort_id} not found")

    # 참가자의 user / infra 존재 검증
    for p in participants:
        u = await session.get(User, p["user_id"])
        if not u:
            raise ValueError(f"user {p['user_id']} not found")
        if p.get("infra_id") is not None:
            inf = await session.get(Infra, p["infra_id"])
            if not inf or inf.owner_id != p["user_id"]:
                raise ValueError(f"infra {p['infra_id']} not owned by user {p['user_id']}")
        else:
            # infra_id 미지정 → 해당 학생이 등록한 인프라를 자동 연결한다.
            # (AI 채점기가 참가자 인프라를 직접 점검해야 하므로, 미연결이면 채점 불능이 된다.)
            own = await session.scalar(
                select(Infra).where(Infra.owner_id == p["user_id"]).order_by(Infra.id.desc()).limit(1)
            )
            if own is not None:
                p["infra_id"] = own.id

    apps = [a.lower() for a in (target_apps or [])]
    if apps == ["random"]:
        import random
        apps = random.sample(sorted(VALID_TARGET_APPS), k=random.randint(2, 4))
    else:
        bad = [a for a in apps if a not in VALID_TARGET_APPS]
        if bad:
            raise ValueError(f"unknown target_apps: {bad}. valid: {sorted(VALID_TARGET_APPS)}")
        if len(apps) > 5:
            raise ValueError("max 5 target_apps (or ['random'])")

    battle = Battle(
        scenario_id=scenario_id,
        cohort_id=cohort_id,
        mode=mode,
        monitor=monitor,
        target_apps=apps,
        hint_enabled=bool(hint_enabled),
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


async def join_battle(
    session: AsyncSession, *, battle_id: int, user_id: int,
    role: str, infra_id: int | None,
) -> Battle:
    b = await session.get(Battle, battle_id)
    if not b:
        raise ValueError(f"battle {battle_id} not found")
    if b.status not in ("pending",):
        raise ValueError(f"battle {battle_id} already {b.status} — join 불가")

    # 참가자 목록 + 역할 검증
    existing = (await session.scalars(
        select(BattleParticipant).where(BattleParticipant.battle_id == battle_id)
    )).all()
    if any(p.user_id == user_id for p in existing):
        raise ValueError("already joined this battle")

    # mode 별 join 규칙
    roles_now = [p.role for p in existing]
    if b.mode == "solo":
        raise ValueError("solo battle has no lobby — only the creator can play")
    if b.mode == "duel":
        if len(existing) >= 2:
            raise ValueError("duel battle full")
        if role not in ("red", "blue"):
            raise ValueError("duel role must be red or blue")
        if role in roles_now:
            raise ValueError(f"duel role '{role}' already taken — choose the other side")
    elif b.mode == "ffa":
        if role not in ("free", "red", "blue"):
            raise ValueError("ffa role must be free/red/blue")
        if len(existing) >= 16:
            raise ValueError("ffa battle full (16 max)")

    # infra 검증 — owner 일치
    if infra_id is not None:
        inf = await session.get(Infra, infra_id)
        if not inf or inf.owner_id != user_id:
            raise ValueError(f"infra {infra_id} not owned by user {user_id}")

    session.add(BattleParticipant(
        battle_id=battle_id, user_id=user_id, infra_id=infra_id, role=role, score=0,
    ))
    session.add(BattleEvent(
        battle_id=battle_id, actor_user_id=user_id,
        event_type="system", target="lobby",
        description=f"user #{user_id} joined as {role}",
        points=0,
    ))
    await session.commit()
    return await load_battle(session, battle_id)


async def leave_battle(
    session: AsyncSession, *, battle_id: int, user_id: int,
) -> Battle:
    b = await session.get(Battle, battle_id)
    if not b:
        raise ValueError(f"battle {battle_id} not found")
    if b.status != "pending":
        raise ValueError("only pending lobby battles can be left")
    p = await session.scalar(
        select(BattleParticipant).where(
            BattleParticipant.battle_id == battle_id,
            BattleParticipant.user_id == user_id,
        )
    )
    if not p:
        raise ValueError("not a participant")
    role = p.role
    await session.delete(p)
    session.add(BattleEvent(
        battle_id=battle_id, actor_user_id=user_id,
        event_type="system", target="lobby",
        description=f"user #{user_id} left ({role})",
        points=0,
    ))
    await session.commit()
    return await load_battle(session, battle_id)


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
    parts = (await session.scalars(
        select(BattleParticipant).where(BattleParticipant.battle_id == battle_id)
    )).all()
    validate_can_start(b.mode, [{"role": p.role, "user_id": p.user_id} for p in parts])
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
    actor_user_id: int | None,
    event_type: str,
    target: str,
    description: str,
    points: int,
    detail: dict,
    reasoning: str | None = None,
    enforce_time_limit: bool = True,
) -> BattleEvent:
    """이벤트 추가 + actor 점수 반영 + (옵션) 시간 만료 시 자동 종료.

    enforce_time_limit=False: 백그라운드 채점처럼 *비동기로 늦게 도착*하는 시스템 기록
    이벤트가 배틀을 소급 종료시키지 않게 한다(학생이 다음 미션 작업 중인데 채점 완료
    순간 제출 폼이 사라지는 문제 방지). 종료는 실시간 타이머/수동/auto-monitor 가 담당.
    """
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
        reasoning=reasoning,
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
    if enforce_time_limit and started and b.time_limit_sec > 0:
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
