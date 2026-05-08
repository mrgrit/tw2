"""Pydantic 입출력 스키마."""
from __future__ import annotations
import datetime as dt
from typing import Any
from pydantic import BaseModel, EmailStr, Field


# ── Auth ─────────────────────────────────────────────
class SignupIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=120)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserOut"


class UserOut(BaseModel):
    id: int
    email: str
    name: str
    role: str
    is_active: bool
    created_at: dt.datetime

    model_config = {"from_attributes": True}


# ── Infra ────────────────────────────────────────────
class InfraIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    vm_ip: str = Field(min_length=3, max_length=45)
    ssh_user: str = Field(default="ccc", max_length=40)
    ssh_password: str = Field(min_length=1, max_length=255)
    bastion_api_key: str = Field(default="ccc-api-key-2026", max_length=120)
    # 학생 6v6 의 .env (PORT_HTTP, PORT_BASTION_API 등) 가 default 와 다를 때만 채움.
    port_map: dict[str, int] = Field(default_factory=dict)


class InfraOut(BaseModel):
    id: int
    name: str
    vm_ip: str
    ssh_user: str
    bastion_api_key: str
    port_map: dict[str, int]
    status: str
    last_smoke_at: dt.datetime | None
    last_smoke_result: dict[str, Any] | None
    created_at: dt.datetime

    model_config = {"from_attributes": True}


class SmokeResult(BaseModel):
    ok: bool
    checks: list[dict[str, Any]]
    summary: str


# ── Battle / Scenario (Phase 1 placeholder) ──────────
class ScenarioOut(BaseModel):
    id: int
    title: str
    description: str
    source: str
    status: str
    time_limit_sec: int
    created_at: dt.datetime

    model_config = {"from_attributes": True}


class BattleOut(BaseModel):
    id: int
    scenario_id: int | None
    mode: str
    status: str
    monitor: str
    target_apps: list[str] = Field(default_factory=list)
    hint_enabled: bool = False
    started_at: dt.datetime | None
    ended_at: dt.datetime | None
    time_limit_sec: int
    created_at: dt.datetime

    model_config = {"from_attributes": True}


class BattleParticipantIn(BaseModel):
    user_id: int
    role: str = Field(pattern=r"^(red|blue|solo|free|observer)$")
    infra_id: int | None = None


class BattleParticipantOut(BaseModel):
    id: int
    user_id: int
    infra_id: int | None
    role: str
    score: int

    model_config = {"from_attributes": True}


class BattleCreateIn(BaseModel):
    scenario_id: int
    mode: str = Field(pattern=r"^(solo|duel|ffa)$")
    monitor: str = Field(default="bastion", pattern=r"^(bastion|claude)$")
    # 6v6 8개 취약 웹 중 1~5 또는 ['random']. 빈 리스트면 시나리오 default 사용.
    target_apps: list[str] = Field(default_factory=list, max_length=8)
    hint_enabled: bool = Field(default=False)
    # admin 이 lobby (참가자 0명) 로 만들 수 있도록 min_length=0. 런타임에서 mode 별 검증.
    participants: list[BattleParticipantIn] = Field(default_factory=list, max_length=16)


class BattleEventIn(BaseModel):
    event_type: str = Field(min_length=1, max_length=24)
    target: str = Field(default="", max_length=120)
    description: str = Field(default="", max_length=2000)
    points: int = Field(default=0, ge=-100, le=200)
    detail: dict[str, Any] = Field(default_factory=dict)


class BattleEventOut(BaseModel):
    id: int
    actor_user_id: int | None
    event_type: str
    target: str
    description: str
    detail: dict[str, Any]
    reasoning: str | None = None
    points: int
    ts: dt.datetime

    model_config = {"from_attributes": True}


class MissionOut(BaseModel):
    """학생/관전자에게 노출되는 미션 카드."""
    side: str                                     # red | blue
    order: int
    title: str | None = None
    instruction: str
    target_vm: str | None = None
    points: int = 0
    hint: str | None = None
    verify_expect: str | None = None              # mission.verify.expect (refined 우선)
    semantic_intent: str | None = None            # mission.verify.semantic.intent
    success_criteria: list[str] = Field(default_factory=list)
    solved: bool = False                          # auto-monitor 가 매칭한 적 있나


class BattleDetail(BaseModel):
    battle: BattleOut
    scenario_title: str | None
    participants: list[BattleParticipantOut]
    events: list[BattleEventOut]
    elapsed_sec: float
    remaining_sec: float
    my_role: str | None = None                    # 본인의 role (참가자) / None (관전)
    my_missions: list[MissionOut] = Field(default_factory=list)         # 내 역할 미션
    opponent_missions: list[MissionOut] = Field(default_factory=list)   # 상대편 (관전자=양쪽)


class BattleJoinIn(BaseModel):
    role: str = Field(pattern=r"^(red|blue|free)$")
    infra_id: int | None = None


TokenOut.model_rebuild()
