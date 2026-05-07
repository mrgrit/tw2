"""ORM 모델 — Phase 1 골격.

학생 ↔ 관리자, 학생의 6v6 인프라, 공방전, 시나리오, 스크랩 게시판.
Phase 2 이후: 인증 자격 암호화, 시나리오 missions JSONB 스키마 정식화.
"""
from __future__ import annotations
import datetime as dt
from sqlalchemy import (
    JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, func,
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


class Scenario(Base):
    """공방전 시나리오 — admin 직접 작성 또는 Claude Code 자동 생성 (Phase 4)."""
    __tablename__ = "scenarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    source: Mapped[str] = mapped_column(String(40), default="admin", nullable=False)  # admin | claude | bastion-scrap
    course_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)        # e.g. "course3 / w01-w03"
    mission_red: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    mission_blue: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    scoring: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    time_limit_sec: Mapped[int] = mapped_column(Integer, default=1800, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False)  # draft | validated | active | archived
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Battle(Base):
    """진행/종료된 공방전 인스턴스."""
    __tablename__ = "battles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scenario_id: Mapped[int | None] = mapped_column(ForeignKey("scenarios.id", ondelete="SET NULL"))
    mode: Mapped[str] = mapped_column(String(16), nullable=False)         # solo | duel | ffa
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)  # pending | active | completed | cancelled
    monitor: Mapped[str] = mapped_column(String(16), default="bastion", nullable=False)  # bastion | claude
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
    points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ts: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    battle: Mapped["Battle"] = relationship(back_populates="events")


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
