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


class GoogleAuthIn(BaseModel):
    # GIS 가 발급한 ID 토큰(credential).
    credential: str = Field(min_length=10, max_length=8192)


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


# ── Cohort (위계 트리) ───────────────────────────────
_COHORT_KIND = r"^(department|grade|course|section|team)$"
_MEMBER_ROLE = r"^(student|instructor|ta)$"


class CohortIn(BaseModel):
    kind: str = Field(pattern=_COHORT_KIND)
    name: str = Field(min_length=1, max_length=120)
    parent_id: int | None = None
    course_ref: str | None = Field(default=None, max_length=120)


class CohortPatchIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    parent_id: int | None = None
    course_ref: str | None = Field(default=None, max_length=120)


class CohortOut(BaseModel):
    id: int
    kind: str
    name: str
    parent_id: int | None
    course_ref: str | None
    created_at: dt.datetime
    member_count: int = 0

    model_config = {"from_attributes": True}


class CohortTreeOut(CohortOut):
    """서브트리 조회용 — children 을 재귀로 포함."""
    children: list["CohortTreeOut"] = Field(default_factory=list)


class CohortMembershipIn(BaseModel):
    user_id: int
    role: str | None = Field(default=None, pattern=_MEMBER_ROLE)


class CohortMembershipOut(BaseModel):
    id: int
    cohort_id: int
    user_id: int
    user_name: str | None = None
    user_email: str | None = None
    role: str | None = None
    created_at: dt.datetime

    model_config = {"from_attributes": True}


class CohortMoveIn(BaseModel):
    """학생을 한 Cohort 에서 다른 Cohort 로 이동."""
    user_id: int
    from_cohort_id: int
    to_cohort_id: int
    role: str | None = Field(default=None, pattern=_MEMBER_ROLE)


# ── Battle / Scenario (Phase 1 placeholder) ──────────
class ScenarioOut(BaseModel):
    id: int
    title: str
    description: str
    source: str
    category: str | None = None
    status: str
    time_limit_sec: int
    grader_profile_id: int | None = None
    created_at: dt.datetime

    model_config = {"from_attributes": True}


class BattleOut(BaseModel):
    id: int
    scenario_id: int | None
    scenario_title: str | None = None
    cohort_id: int | None = None
    cohort_name: str | None = None
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
    # 수업용 배틀이면 Cohort(보통 section/team) 지정, 신원-only 면 None.
    cohort_id: int | None = None
    mode: str = Field(pattern=r"^(solo|duel|ffa)$")
    monitor: str = Field(default="bastion", pattern=r"^(bastion|claude)$")
    # 6v6 8개 취약 웹 중 1~5 또는 ['random']. 빈 리스트면 시나리오 default 사용.
    target_apps: list[str] = Field(default_factory=list, max_length=8)
    hint_enabled: bool = Field(default=False)
    # admin 이 lobby (참가자 0명) 로 만들 수 있도록 min_length=0. 런타임에서 mode 별 검증.
    participants: list[BattleParticipantIn] = Field(default_factory=list, max_length=16)


class BattleEventIn(BaseModel):
    """학생/관리자가 보고하는 이벤트.

    Phase 9.3: analyzer 가 채점 근거를 LLM 분석으로 만들 수 있도록 학생 보고 정보를 풍부화.
    `mission_order` 가 있으면 해당 미션의 success_criteria 기준으로 분석. 없으면 일반 평가.
    """
    event_type: str = Field(min_length=1, max_length=24)
    target: str = Field(default="", max_length=120)
    description: str = Field(default="", max_length=2000)
    points: int = Field(default=0, ge=-100, le=200)
    # 어느 미션에 대한 보고인가 (있으면 해당 미션 기준 분석)
    mission_order: int | None = Field(default=None, ge=1, le=99)
    mission_side: str | None = Field(default=None, pattern=r"^(red|blue)$")
    # 학생이 실제로 사용한 명령/페이로드 (시도 내역)
    what_i_did: str = Field(default="", max_length=4000)
    # 결과/응답 (출력 발췌)
    what_happened: str = Field(default="", max_length=4000)
    # legacy / 자유 detail (자동 모니터가 사용)
    detail: dict[str, Any] = Field(default_factory=dict)
    # 멱등키 — 프런트가 제출마다 발급. 더블클릭/재전송이 중복 채점을 만들지 않게.
    client_token: str | None = Field(default=None, max_length=64)


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


class StudentSubmissionOut(BaseModel):
    """학생 제출 저널 한 건 — verbatim 입력 + (있으면) 채점 결과. 포트폴리오/워크북의 원천."""
    id: int
    user_id: int
    battle_id: int | None = None
    scenario_id: int | None = None
    mission_side: str | None = None
    mission_order: int | None = None
    event_type: str
    target: str
    what_i_did: str
    what_happened: str
    description: str
    claimed_points: int
    mission_snapshot: dict[str, Any] = Field(default_factory=dict)
    grade_status: str                       # pending | graded | failed
    verdict: str | None = None
    awarded_points: int | None = None
    max_points: int | None = None
    feedback: str | None = None
    criteria_met: list[Any] = Field(default_factory=list)
    criteria_missing: list[Any] = Field(default_factory=list)
    grader_model: str | None = None
    battle_event_id: int | None = None
    submitted_at: dt.datetime
    graded_at: dt.datetime | None = None

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
    # Assessor check-spec[] (compile 결과 캐시) + 채점 대상(self|opponent)
    checks: list[dict[str, Any]] = Field(default_factory=list)
    assess_target: str = "self"                   # self | opponent
    arm_rule: dict[str, Any] | None = None        # (옵션) 룰 무장 템플릿 참조
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


# ── 활동 / 진도 / 피드백 ─────────────────────────────
class ActivityEventOut(BaseModel):
    id: int
    battle_id: int | None
    cohort_id: int | None
    user_id: int | None
    infra_id: int | None
    kind: str
    scenario_step: int | None
    payload: dict[str, Any]
    ts: dt.datetime

    model_config = {"from_attributes": True}


class StudentProgressOut(BaseModel):
    user_id: int
    name: str | None = None
    completion: float = 0.0
    steps_done: int = 0
    steps_total: int = 0
    bottleneck_flags: dict[str, Any] = Field(default_factory=dict)
    stuck: bool = False
    last_activity_ts: dt.datetime | None = None


class CohortProgressOut(BaseModel):
    cohort_id: int | None
    battle_id: int | None
    steps_total: int
    students: list[StudentProgressOut] = Field(default_factory=list)


class StudentFeedbackOut(BaseModel):
    id: int
    user_id: int
    cohort_id: int | None
    battle_id: int | None
    scope: str
    trigger: str
    content_md: str
    basis: dict[str, Any]
    model: str
    cost_usd: float
    delivered_to: str
    created_at: dt.datetime

    model_config = {"from_attributes": True}


class FeedbackCreateIn(BaseModel):
    battle_id: int | None = None
    cohort_id: int | None = None
    scope: str = Field(default="lab", pattern=r"^(lab|session|periodic)$")
    delivered_to: str = Field(default="both", pattern=r"^(student|instructor|both)$")
    note: str = Field(default="", max_length=1000)


# ── 채점 AI 프로필 (시나리오별 등록/선택) ─────────────
class GraderProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    provider: str = Field(pattern=r"^(cc|bastion)$")
    model: str = Field(min_length=1, max_length=80)
    base_url: str | None = Field(default=None, max_length=200)   # bastion 필수
    api_key: str | None = Field(default=None, max_length=200)
    enabled: bool = True
    is_default: bool = False


class GraderProfilePatchIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    provider: str | None = Field(default=None, pattern=r"^(cc|bastion)$")
    model: str | None = Field(default=None, min_length=1, max_length=80)
    base_url: str | None = Field(default=None, max_length=200)
    api_key: str | None = Field(default=None, max_length=200)
    enabled: bool | None = None
    is_default: bool | None = None


class GraderProfileOut(BaseModel):
    id: int
    name: str
    provider: str
    model: str
    base_url: str | None
    has_api_key: bool = False        # 키 자체는 노출하지 않음
    enabled: bool
    is_default: bool
    created_at: dt.datetime

    model_config = {"from_attributes": True}


TokenOut.model_rebuild()
CohortTreeOut.model_rebuild()
