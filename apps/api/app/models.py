"""ORM 모델 — Phase 1 골격.

학생 ↔ 관리자, 학생의 6v6 인프라, 공방전, 시나리오, 스크랩 게시판.
Phase 2 이후: 인증 자격 암호화, 시나리오 missions JSONB 스키마 정식화.
"""
from __future__ import annotations
import datetime as dt
from sqlalchemy import (
    JSON, Boolean, DateTime, ForeignKey, Integer, String, Text,
    UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(16), default="student", nullable=False)  # student | admin
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # 인증 출처 — local(이메일/비번) | google. 구글 연결 시 google_sub 채움.
    auth_provider: Mapped[str] = mapped_column(String(16), default="local", nullable=False)
    google_sub: Mapped[str | None] = mapped_column(String(64), unique=True, index=True, nullable=True)
    # 개인 GPU(Ollama) 서버 — 드래그-질문 AI 튜터가 사용. url 예: http://1.2.3.4:11434
    llm_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    llm_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    infras: Mapped[list["Infra"]] = relationship(back_populates="owner", cascade="all,delete")


class Infra(Base):
    """학생 1명이 등록한 1세트의 6v6 VM (단일 VM 안의 13 컨테이너)."""
    __tablename__ = "infras"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)         # alias e.g. "alice-6v6"
    vm_ip: Mapped[str] = mapped_column(String(45), nullable=False)        # IPv4/IPv6
    ssh_user: Mapped[str] = mapped_column(String(40), default="ccc", nullable=False)
    ssh_password_enc: Mapped[str] = mapped_column(String(255), nullable=False)  # TODO Phase 2 암호화
    bastion_api_key: Mapped[str] = mapped_column(String(120), nullable=False)
    # 학생이 6v6 docker-compose 의 .env 로 외부 포트를 override 한 경우를 위한 매핑.
    # 키: http, https, bastion_ssh, attacker_ssh, portal, siem_lite, bastion_api
    port_map: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="registered", nullable=False)
    last_smoke_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_smoke_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    owner: Mapped["User"] = relationship(back_populates="infras")


class Cohort(Base):
    """수강 위계 트리 노드 (학과–학년–교과목–분반–팀).

    자기참조 트리: parent_id 로 상위 노드를 가리킨다. 학생은 CohortMembership 으로
    트리의 임의 노드(보통 team/section)에 연결된다. course_ref 는 Scenario.course_ref 와
    느슨하게 연결되어 교과목 단위 시나리오 매칭에 쓰인다.
    """
    __tablename__ = "cohorts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # department | grade | course | section | team
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("cohorts.id", ondelete="CASCADE"), index=True, nullable=True
    )
    # Scenario.course_ref 와 느슨한 연결 (교과목 노드에서 주로 사용)
    course_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    parent: Mapped["Cohort | None"] = relationship(
        back_populates="children", remote_side="Cohort.id"
    )
    children: Mapped[list["Cohort"]] = relationship(
        back_populates="parent", cascade="all,delete-orphan"
    )
    memberships: Mapped[list["CohortMembership"]] = relationship(
        back_populates="cohort", cascade="all,delete-orphan"
    )


class CohortMembership(Base):
    """학생 ↔ Cohort 노드 다대다 연결.

    학생이 학기·분반을 옮기거나 수업 밖에서 재사용돼도 무방하도록 다대다로 모델링.
    동일 (cohort, user) 조합은 unique.
    """
    __tablename__ = "cohort_memberships"
    __table_args__ = (
        UniqueConstraint("cohort_id", "user_id", name="uq_cohort_user"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cohort_id: Mapped[int] = mapped_column(
        ForeignKey("cohorts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    role: Mapped[str | None] = mapped_column(String(16), nullable=True)  # student | instructor | ta
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    cohort: Mapped["Cohort"] = relationship(back_populates="memberships")


class Scenario(Base):
    """공방전 시나리오 — admin 직접 작성 또는 Claude Code 자동 생성 (Phase 4)."""
    __tablename__ = "scenarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    source: Mapped[str] = mapped_column(String(40), default="admin", nullable=False)  # admin | claude | bastion-scrap
    # 교과목 카테고리 — UI 그룹핑/필터용 (secuops-easy | secuops | soc | attack | ...). null=미분류
    category: Mapped[str | None] = mapped_column(String(40), nullable=True)
    course_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)        # e.g. "course3 / w01-w03"
    mission_red: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    mission_blue: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    scoring: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    time_limit_sec: Mapped[int] = mapped_column(Integer, default=1800, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False)  # draft | validated | active | archived
    # 이 시나리오를 채점할 AI 프로필 (null → 기본 프로필 → CC fallback)
    grader_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("grader_profiles.id", ondelete="SET NULL"), nullable=True
    )
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class GraderProfile(Base):
    """채점 AI 프로필 — 시나리오별로 등록/선택. provider=cc(Claude Code) | bastion(6v6 LLM).

    - cc: claude CLI (`model` 예: claude-haiku-4-5, claude-opus-4-8). base_url 불필요.
    - bastion: 6v6 Bastion 의 LLM API (ollama 호환 /api/generate). `base_url` 예: http://10.0.0.x:9100,
      `model` 예: gpt-oss:120b / gemma3:4b. `api_key` = X-API-Key.
    """
    __tablename__ = "grader_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(16), nullable=False)   # cc | bastion
    model: Mapped[str] = mapped_column(String(80), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(200), nullable=True)   # bastion LLM endpoint
    api_key: Mapped[str | None] = mapped_column(String(200), nullable=True)    # bastion X-API-Key
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Battle(Base):
    """진행/종료된 공방전 인스턴스."""
    __tablename__ = "battles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scenario_id: Mapped[int | None] = mapped_column(ForeignKey("scenarios.id", ondelete="SET NULL"))
    # 수업용 배틀이면 Cohort(보통 section/team) 설정, 신원-only 모드면 null.
    cohort_id: Mapped[int | None] = mapped_column(
        ForeignKey("cohorts.id", ondelete="SET NULL"), index=True, nullable=True
    )
    mode: Mapped[str] = mapped_column(String(16), nullable=False)         # solo | duel | ffa
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)  # pending | active | completed | cancelled
    monitor: Mapped[str] = mapped_column(String(16), default="bastion", nullable=False)  # bastion | claude
    # Phase 9: 공방전 옵션
    target_apps: Mapped[list] = mapped_column(JSON, default=list, nullable=False)   # ['juiceshop', 'dvwa', ...] 또는 ['random']
    hint_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    time_limit_sec: Mapped[int] = mapped_column(Integer, default=1800, nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    participants: Mapped[list["BattleParticipant"]] = relationship(
        back_populates="battle", cascade="all,delete"
    )
    events: Mapped[list["BattleEvent"]] = relationship(
        back_populates="battle", cascade="all,delete"
    )


class BattleParticipant(Base):
    __tablename__ = "battle_participants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    battle_id: Mapped[int] = mapped_column(ForeignKey("battles.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    infra_id: Mapped[int | None] = mapped_column(ForeignKey("infras.id", ondelete="SET NULL"))
    role: Mapped[str] = mapped_column(String(16), nullable=False)         # red | blue | observer | admin
    score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    battle: Mapped["Battle"] = relationship(back_populates="participants")


class BattleEvent(Base):
    __tablename__ = "battle_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    battle_id: Mapped[int] = mapped_column(ForeignKey("battles.id", ondelete="CASCADE"), index=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    event_type: Mapped[str] = mapped_column(String(24), nullable=False)
    target: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    detail: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    # Phase 9: LLM 자연어 채점 근거 보고서 (markdown 가능)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ts: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    battle: Mapped["Battle"] = relationship(back_populates="events")


class BattleHint(Base):
    """학생이 명시 요청 시 LLM 이 생성한 힌트. 동일 (battle, mission) 캐시 + cooldown 추적."""
    __tablename__ = "battle_hints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    battle_id: Mapped[int] = mapped_column(ForeignKey("battles.id", ondelete="CASCADE"), index=True)
    requested_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    mission_side: Mapped[str] = mapped_column(String(8), default="any", nullable=False)  # red | blue | any
    mission_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    probe_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)  # 동일 상태 캐시
    text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    model: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    cost_usd: Mapped[float] = mapped_column(Integer, default=0, nullable=False)  # int 로 충분 (cents)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AuditLog(Base):
    """관리자 행동 + 보안 이벤트 감사 로그 (Phase 8)."""
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    actor_email: Mapped[str | None] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(40))
    target_id: Mapped[str | None] = mapped_column(String(80))
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(255))
    detail: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    ts: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )


class ActivityEvent(Base):
    """학생 infra 의 Assessor `/activity` 에서 pull 한 활동 1건 (명령/파일변경/알림/로그).

    lab_monitor 가 N초 간격으로 적재. battle/scenario step·cohort 문맥은 서버측 태깅
    (Battle→Scenario step·Cohort). 진도·병목 산출과 중앙 SIEM 적재의 원천.
    """
    __tablename__ = "activity_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    battle_id: Mapped[int | None] = mapped_column(
        ForeignKey("battles.id", ondelete="CASCADE"), index=True, nullable=True
    )
    cohort_id: Mapped[int | None] = mapped_column(
        ForeignKey("cohorts.id", ondelete="SET NULL"), index=True, nullable=True
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    infra_id: Mapped[int | None] = mapped_column(
        ForeignKey("infras.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # command | fim | alert | log | service
    scenario_step: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 활동 식별용 dedupe 키 (같은 명령/알림 재pull 시 중복 적재 방지)
    dedupe_key: Mapped[str | None] = mapped_column(String(80), index=True, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    ts: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ProgressSnapshot(Base):
    """lab_monitor 가 산출한 학생별 진도/병목 스냅샷."""
    __tablename__ = "progress_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    battle_id: Mapped[int | None] = mapped_column(
        ForeignKey("battles.id", ondelete="CASCADE"), index=True, nullable=True
    )
    cohort_id: Mapped[int | None] = mapped_column(
        ForeignKey("cohorts.id", ondelete="SET NULL"), index=True, nullable=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    completion: Mapped[float] = mapped_column(Integer, default=0, nullable=False)  # 0..100 (%)
    steps_done: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    steps_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bottleneck_flags: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    ts: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class StudentFeedback(Base):
    """CC(claude/haiku)가 작성한 학생별 개인화 피드백."""
    __tablename__ = "student_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    cohort_id: Mapped[int | None] = mapped_column(
        ForeignKey("cohorts.id", ondelete="SET NULL"), index=True, nullable=True
    )
    battle_id: Mapped[int | None] = mapped_column(
        ForeignKey("battles.id", ondelete="SET NULL"), nullable=True
    )
    scope: Mapped[str] = mapped_column(String(16), default="lab", nullable=False)  # lab | session | periodic
    trigger: Mapped[str] = mapped_column(String(24), default="manual", nullable=False)  # bottleneck | end | manual
    content_md: Mapped[str] = mapped_column(Text, default="", nullable=False)
    basis: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)  # 진도·bottleneck·참조 event ids
    model: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    cost_usd: Mapped[float] = mapped_column(Integer, default=0, nullable=False)
    delivered_to: Mapped[str] = mapped_column(String(16), default="student", nullable=False)  # student|instructor|both
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ScrapPost(Base):
    """Bastion 이 외부 커뮤니티/뉴스에서 스크랩한 침해사고/AI 위협 게시글 (Phase 5)."""
    __tablename__ = "scrap_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(80), nullable=False)         # url 도메인/feed 명
    source_url: Mapped[str] = mapped_column(String(500), nullable=False)
    title: Mapped[str] = mapped_column(String(400), nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    relevance: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)  # KG 매칭/판단 근거
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)  # pending | approved | rejected
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    decided_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    spawned_scenario_id: Mapped[int | None] = mapped_column(ForeignKey("scenarios.id", ondelete="SET NULL"))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class StudentSubmission(Base):
    """학생 제출 저널 — append-only. '내가 한 일' 보고를 제출 즉시 **verbatim** 보존하고,
    AI 채점 결과(verdict/점수/피드백)를 나중에 같은 행에 비동기로 붙인다.

    설계 의도:
    - battle/scenario 가 삭제돼도(SET NULL) **학생 소유 기록은 생존** → 복습·포트폴리오·워크북의 단일 원천.
    - 입력(what_i_did/what_happened/description/claimed)은 절대 수정·절삭하지 않는다(워크북 빈칸과 1:1).
    - `mission_snapshot`: 제출 당시 학생이 본 미션 지시문 사본(시나리오가 나중에 바뀌어도 맥락 보존).
    - `grade_status`: pending → graded | failed. 채점 지연/실패와 무관하게 입력은 항상 남는다.
    - `client_token`: 프런트 발급 멱등키 — 더블클릭/재전송이 중복 채점 잡을 만들지 않게.
    - `battle_events` 가 점수의 '권위' 기록, 이 테이블은 학생 학습 관점의 영속 저널(상호 보완).
    """
    __tablename__ = "student_submissions"
    __table_args__ = (UniqueConstraint("client_token", name="uq_submission_client_token"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    battle_id: Mapped[int | None] = mapped_column(
        ForeignKey("battles.id", ondelete="SET NULL"), index=True, nullable=True)
    scenario_id: Mapped[int | None] = mapped_column(
        ForeignKey("scenarios.id", ondelete="SET NULL"), index=True, nullable=True)
    cohort_id: Mapped[int | None] = mapped_column(
        ForeignKey("cohorts.id", ondelete="SET NULL"), nullable=True)
    # ── 미션 좌표 + 학생 입력 (verbatim, 불변) ──
    mission_side: Mapped[str | None] = mapped_column(String(8), nullable=True)    # red | blue | None
    mission_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    event_type: Mapped[str] = mapped_column(String(24), default="", nullable=False)
    target: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    what_i_did: Mapped[str] = mapped_column(Text, default="", nullable=False)        # ▶ 실행한 명령/페이로드
    what_happened: Mapped[str] = mapped_column(Text, default="", nullable=False)     # ▶ 실행 결과
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)        # ▶ 설명/분석
    claimed_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    mission_snapshot: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)  # {title,instruction,points,target_vm}
    # ── 채점 결과 (나중에 비동기로 붙음) ──
    grade_status: Mapped[str] = mapped_column(String(12), default="pending", nullable=False)  # pending|graded|failed
    verdict: Mapped[str | None] = mapped_column(String(16), nullable=True)
    awarded_points: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_points: Mapped[int | None] = mapped_column(Integer, nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)                 # AI 채점 근거(markdown)
    criteria_met: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    criteria_missing: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    grader_model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    battle_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("battle_events.id", ondelete="SET NULL"), nullable=True)          # 점수 권위 event 연결
    client_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    submitted_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
    graded_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
