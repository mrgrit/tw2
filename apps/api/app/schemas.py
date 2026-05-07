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
    participants: list[BattleParticipantIn] = Field(min_length=1, max_length=16)


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
    points: int
    ts: dt.datetime

    model_config = {"from_attributes": True}


class BattleDetail(BaseModel):
    battle: BattleOut
    scenario_title: str | None
    participants: list[BattleParticipantOut]
    events: list[BattleEventOut]
    elapsed_sec: float
    remaining_sec: float


TokenOut.model_rebuild()
