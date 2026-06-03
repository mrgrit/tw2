"""auto_monitor — Assessor 기반 blue 자동 채점, heartbeat collapse, monitor 분기."""
from __future__ import annotations
import os
import pytest
import pytest_asyncio

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("TUBEWAR_JWT_SECRET", "test-secret-32-chars-please-not-shorter")
os.environ.setdefault("TUBEWAR_FERNET_KEY", "ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg=")

from sqlalchemy import select  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.models import Battle, BattleEvent, BattleParticipant, Infra, Scenario, User  # noqa: E402
from app.security import hash_password  # noqa: E402
from app.services import battle_service as bs, auto_monitor, grader  # noqa: E402
from app.services import assessor_client, event_analyzer as ea  # noqa: E402
from tests.assessor_fake import build_fake_assess  # noqa: E402


@pytest_asyncio.fixture(autouse=True)
async def _reset(monkeypatch):
    # 이 모듈은 자동채점 '메커니즘'을 검증하므로 명시적으로 ON (기본은 OFF).
    monkeypatch.setenv("TUBEWAR_AUTO_SCORE", "1")
    auto_monitor._seen_hits.clear()
    auto_monitor._locks.clear()
    grader._judge_cache.clear()
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.drop_all)
    auto_monitor._seen_hits.clear()
    auto_monitor._locks.clear()
    grader._judge_cache.clear()


def _blue_mission(order=1, points=15):
    return {"order": order, "instruction": "auth.log Failed password 분석", "points": points,
            "target_vm": "web",
            "verify": {"type": "output_contains", "expect": "Failed",
                       "semantic": {"success_criteria": ["/var/log/auth.log Failed password"]}}}


async def _make_solo_battle(monitor="bastion", blue_missions=None):
    async with SessionLocal() as s:
        u = User(email="a@example.com", name="A", password_hash=hash_password("pass1234"))
        s.add(u)
        await s.flush()
        inf = Infra(owner_id=u.id, name="a-6v6", vm_ip="10.20.30.80",
                    ssh_password_enc="x", bastion_api_key="k", port_map={})
        s.add(inf)
        scn = Scenario(title="T", status="validated",
                       mission_red={"missions": []},
                       mission_blue={"missions": blue_missions or [_blue_mission()]},
                       scoring={}, time_limit_sec=1800)
        s.add(scn)
        await s.flush()
        b = await bs.create_battle(
            s, scenario_id=scn.id, mode="solo", monitor=monitor,
            participants=[{"user_id": u.id, "role": "solo", "infra_id": inf.id}],
            created_by=u.id,
        )
        await bs.start_battle(s, b.id, actor_user_id=u.id)
        return b.id, u.id


async def _events(battle_id):
    async with SessionLocal() as s:
        return (await s.scalars(
            select(BattleEvent).where(BattleEvent.battle_id == battle_id)
            .order_by(BattleEvent.id.asc())
        )).all()


async def _score(battle_id, role="solo"):
    async with SessionLocal() as s:
        p = await s.scalar(select(BattleParticipant).where(
            BattleParticipant.battle_id == battle_id, BattleParticipant.role == role))
        return p.score


@pytest.mark.asyncio
async def test_blue_auto_scored_via_assessor_bastion_llm0(monkeypatch):
    bid, uid = await _make_solo_battle(monitor="bastion")
    monkeypatch.setattr(assessor_client, "assess", build_fake_assess())  # 전부 passed
    await auto_monitor.run_once(bid, tick_idx=1)

    evs = await _events(bid)
    detects = [e for e in evs if e.event_type == "detect"]
    assert len(detects) == 1
    e = detects[0]
    assert e.points == 15
    assert e.detail["source"] == "auto_monitor"
    assert e.detail["assessor"] is True
    assert e.detail["model"] == "assessor"      # 결정론 → LLM 0
    assert e.detail["cost_usd"] == 0.0
    assert await _score(bid) == 15


@pytest.mark.asyncio
async def test_dedupe_no_double_score(monkeypatch):
    bid, uid = await _make_solo_battle(monitor="bastion")
    monkeypatch.setattr(assessor_client, "assess", build_fake_assess())
    await auto_monitor.run_once(bid, tick_idx=1)
    await auto_monitor.run_once(bid, tick_idx=2)
    detects = [e for e in await _events(bid) if e.event_type == "detect"]
    assert len(detects) == 1            # 동일 (side, order) 재채점 안 함
    assert await _score(bid) == 15


@pytest.mark.asyncio
async def test_failed_checks_no_score(monkeypatch):
    bid, uid = await _make_solo_battle(monitor="bastion")
    # 모든 check fail
    monkeypatch.setattr(assessor_client, "assess",
                        build_fake_assess(policy=lambda c: (False, "no match")))
    await auto_monitor.run_once(bid, tick_idx=1)
    detects = [e for e in await _events(bid) if e.event_type == "detect"]
    assert detects == []
    assert await _score(bid) == 0


@pytest.mark.asyncio
async def test_heartbeat_collapse_in_place(monkeypatch):
    bid, uid = await _make_solo_battle(monitor="bastion")
    monkeypatch.setattr(assessor_client, "assess",
                        build_fake_assess(policy=lambda c: (False, "no")))  # 점수 안 생김
    await auto_monitor.run_once(bid, tick_idx=4)   # heartbeat 1
    await auto_monitor.run_once(bid, tick_idx=8)   # heartbeat collapse → ticks=2
    hbs = [e for e in await _events(bid)
           if e.event_type == "system" and e.target == "monitor"
           and (e.detail or {}).get("kind") == "heartbeat_range"]
    assert len(hbs) == 1
    assert hbs[0].detail["ticks"] == 2


@pytest.mark.asyncio
async def test_auto_score_off_by_default_no_points(monkeypatch):
    """기본(TUBEWAR_AUTO_SCORE 미설정)에서는 앰비언트 자동 채점이 점수를 주지 않음(공정성)."""
    monkeypatch.delenv("TUBEWAR_AUTO_SCORE", raising=False)
    bid, uid = await _make_solo_battle(monitor="bastion")
    monkeypatch.setattr(assessor_client, "assess", build_fake_assess())  # 전부 passed 여도
    await auto_monitor.run_once(bid, tick_idx=1)
    detects = [e for e in await _events(bid) if e.event_type == "detect"]
    assert detects == []           # 점수 이벤트 없음
    assert await _score(bid) == 0


@pytest.mark.asyncio
async def test_monitor_claude_ambiguous_calls_analyzer(monkeypatch):
    called = {}

    async def fake_analyze(**kw):
        called["hit"] = True
        return ea.AnalysisResult(reasoning="LLM 보강", model="claude-haiku-4-5", cost_usd=0.03)

    monkeypatch.setattr(ea, "analyze_event", fake_analyze)
    bid, uid = await _make_solo_battle(monitor="claude")
    # passed=True 인데 evidence 비어있음 → 모호 → claude 분석
    monkeypatch.setattr(assessor_client, "assess",
                        build_fake_assess(policy=lambda c: (True, "")))
    await auto_monitor.run_once(bid, tick_idx=1)
    detects = [e for e in await _events(bid) if e.event_type == "detect"]
    assert len(detects) == 1
    assert called.get("hit") is True
    assert detects[0].detail["model"] == "claude-haiku-4-5"
