"""battle_engine — 대전 엔진 (인프라 간 공방전)

대전 유형: 1v1, team, ffa
대전 모드: manual, ai, mixed
이벤트 타입: attack, defend, detect, block, exploit, alert, score
"""
from __future__ import annotations
import time
import json
import hashlib
from dataclasses import dataclass, field, asdict
from typing import Any
from enum import Enum


class EventType(str, Enum):
    ATTACK = "attack"
    DEFEND = "defend"
    DETECT = "detect"
    BLOCK = "block"
    EXPLOIT = "exploit"
    ALERT = "alert"
    SCORE = "score"
    SYSTEM = "system"


@dataclass
class BattleEvent:
    """대전 중 발생하는 이벤트"""
    event_type: str          # EventType
    actor: str               # 이벤트 발생 주체 (student_id or "system")
    target: str = ""         # 대상
    description: str = ""
    detail: dict[str, Any] = field(default_factory=dict)
    points: int = 0          # 이 이벤트로 획득/차감되는 점수
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


@dataclass
class BattleState:
    """대전 현재 상태"""
    battle_id: str
    battle_type: str = "1v1"
    mode: str = "manual"
    status: str = "pending"   # pending, active, paused, completed
    challenger_id: str = ""
    defender_id: str = ""
    challenger_score: int = 0
    defender_score: int = 0
    events: list[BattleEvent] = field(default_factory=list)
    rules: dict[str, Any] = field(default_factory=dict)
    started_at: float = 0
    time_limit: int = 300     # seconds
    elapsed: float = 0

    @property
    def time_remaining(self) -> float:
        if self.status != "active":
            return float(self.time_limit)
        return max(0, self.time_limit - (time.time() - self.started_at))

    @property
    def is_expired(self) -> bool:
        return self.status == "active" and self.time_remaining <= 0

    def to_dict(self) -> dict:
        return {
            "battle_id": self.battle_id,
            "battle_type": self.battle_type,
            "mode": self.mode,
            "status": self.status,
            "challenger": {"id": self.challenger_id, "score": self.challenger_score},
            "defender": {"id": self.defender_id, "score": self.defender_score},
            "events_count": len(self.events),
            "time_remaining": round(self.time_remaining, 1),
            "time_limit": self.time_limit,
        }


# ── Battle Manager (in-memory) ────────────────────

_battles: dict[str, BattleState] = {}


def create_battle(
    battle_id: str,
    challenger_id: str,
    defender_id: str = "",
    battle_type: str = "1v1",
    mode: str = "manual",
    rules: dict[str, Any] | None = None,
) -> BattleState:
    rules = rules or {}
    state = BattleState(
        battle_id=battle_id,
        battle_type=battle_type,
        mode=mode,
        challenger_id=challenger_id,
        defender_id=defender_id,
        rules=rules,
        time_limit=rules.get("time_limit", 300),
    )
    _battles[battle_id] = state
    state.events.append(BattleEvent(
        event_type=EventType.SYSTEM, actor="system",
        description=f"Battle created: {challenger_id} vs {defender_id}",
    ))
    return state


def start_battle(battle_id: str) -> BattleState:
    state = _battles.get(battle_id)
    if not state:
        raise ValueError(f"Battle {battle_id} not found")
    state.status = "active"
    state.started_at = time.time()
    state.events.append(BattleEvent(
        event_type=EventType.SYSTEM, actor="system",
        description="Battle started!",
    ))
    return state


def add_event(battle_id: str, event: BattleEvent) -> BattleState:
    """이벤트 추가 + 점수 반영"""
    state = _battles.get(battle_id)
    if not state:
        raise ValueError(f"Battle {battle_id} not found")

    state.events.append(event)

    # 점수 반영
    if event.points != 0:
        if event.actor == state.challenger_id:
            state.challenger_score += event.points
        elif event.actor == state.defender_id:
            state.defender_score += event.points

    # 시간 만료 체크
    if state.is_expired:
        state.status = "completed"
        state.events.append(BattleEvent(
            event_type=EventType.SYSTEM, actor="system",
            description="Time expired!",
        ))

    return state


def end_battle(battle_id: str) -> BattleState:
    state = _battles.get(battle_id)
    if not state:
        raise ValueError(f"Battle {battle_id} not found")
    state.status = "completed"
    state.elapsed = time.time() - state.started_at if state.started_at else 0

    # 승자 판정
    if state.challenger_score > state.defender_score:
        winner = state.challenger_id
    elif state.defender_score > state.challenger_score:
        winner = state.defender_id
    else:
        winner = "draw"

    state.events.append(BattleEvent(
        event_type=EventType.SYSTEM, actor="system",
        description=f"Battle ended! Winner: {winner}",
        detail={"winner": winner, "challenger_score": state.challenger_score, "defender_score": state.defender_score},
    ))
    return state


def get_battle(battle_id: str) -> BattleState | None:
    return _battles.get(battle_id)


def get_events(battle_id: str, since: float = 0) -> list[BattleEvent]:
    """특정 시점 이후 이벤트만 반환 (실시간 스트리밍용)"""
    state = _battles.get(battle_id)
    if not state:
        return []
    return [e for e in state.events if e.timestamp > since]


def get_active_battles() -> list[BattleState]:
    return [s for s in _battles.values() if s.status == "active"]


def get_all_battles() -> list[BattleState]:
    return list(_battles.values())


def generate_battle_hash(state: BattleState) -> str:
    """대전 결과 해시 (블록체인 기록용)"""
    data = f"{state.battle_id}:{state.challenger_id}:{state.defender_id}:{state.challenger_score}:{state.defender_score}:{len(state.events)}"
    return hashlib.sha256(data.encode()).hexdigest()


# ── Statistics ────────────────────────────────────

def battle_stats(battle_id: str) -> dict:
    """대전 통계"""
    state = _battles.get(battle_id)
    if not state:
        return {}

    attacks = [e for e in state.events if e.event_type == EventType.ATTACK]
    defends = [e for e in state.events if e.event_type == EventType.DEFEND]
    detects = [e for e in state.events if e.event_type == EventType.DETECT]
    blocks = [e for e in state.events if e.event_type == EventType.BLOCK]
    exploits = [e for e in state.events if e.event_type == EventType.EXPLOIT]

    return {
        "battle_id": state.battle_id,
        "total_events": len(state.events),
        "attacks": len(attacks),
        "defends": len(defends),
        "detects": len(detects),
        "blocks": len(blocks),
        "exploits": len(exploits),
        "challenger_score": state.challenger_score,
        "defender_score": state.defender_score,
        "duration": round(state.elapsed, 1) if state.elapsed else None,
    }
