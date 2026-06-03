"""cross-infra 듀얼 — assess_target=opponent 해석, 상대 infra 채점, 권한/매칭."""
from __future__ import annotations
import os
import pytest
import pytest_asyncio

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("TUBEWAR_JWT_SECRET", "test-secret-32-chars-please-not-shorter")
os.environ.setdefault("TUBEWAR_FERNET_KEY", "ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg=")

from sqlalchemy import select  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.models import BattleEvent, BattleParticipant, Infra, Scenario, User  # noqa: E402
from app.security import hash_password  # noqa: E402
from app.services import battle_service as bs, auto_monitor, grader, battlefield  # noqa: E402
from app.services import assessor_client  # noqa: E402
from tests.assessor_fake import build_fake_assess  # noqa: E402


# ── 단위: 타깃 infra 해석 ────────────────────────────
class _I:
    def __init__(self, tag):
        self.tag = tag


def test_resolve_target_infra_duel():
    A, B = _I("red"), _I("blue")
    ri = {"red": A, "blue": B}
    assert battlefield.resolve_target_infra("red", "opponent", ri) is B
    assert battlefield.resolve_target_infra("red", "self", ri) is A
    assert battlefield.resolve_target_infra("blue", "self", ri) is B
    assert battlefield.resolve_target_infra("blue", "opponent", ri) is A


def test_resolve_target_infra_solo():
    S = _I("solo")
    ri = {"red": S, "blue": S}
    assert battlefield.resolve_target_infra("red", "opponent", ri) is S
    assert battlefield.resolve_target_infra("blue", "self", ri) is S


def test_normalize_assess_target():
    assert battlefield.normalize_assess_target("opponent") == "opponent"
    assert battlefield.normalize_assess_target("OPPONENT") == "opponent"
    assert battlefield.normalize_assess_target(None) == "self"
    assert battlefield.normalize_assess_target("self") == "self"


# ── 통합: duel cross-infra ───────────────────────────
@pytest_asyncio.fixture(autouse=True)
async def _reset():
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


async def _make_duel(red_assess_target):
    async with SessionLocal() as s:
        red_u = User(email="red@x", name="Red", password_hash=hash_password("pass1234"))
        blue_u = User(email="blue@x", name="Blue", password_hash=hash_password("pass1234"))
        s.add_all([red_u, blue_u])
        await s.flush()
        red_inf = Infra(owner_id=red_u.id, name="red-6v6", vm_ip="10.0.0.1",
                        ssh_password_enc="x", bastion_api_key="k", port_map={})
        blue_inf = Infra(owner_id=blue_u.id, name="blue-6v6", vm_ip="10.0.0.2",
                         ssh_password_enc="x", bastion_api_key="k", port_map={})
        s.add_all([red_inf, blue_inf])
        scn = Scenario(
            title="cross", status="validated",
            mission_red={"missions": [{
                "order": 1, "instruction": "상대 web 을 SQLi 로 공격", "points": 20,
                "target_vm": "web", "assess_target": red_assess_target,
                "verify": {"type": "output_contains", "expect": "SQLi"},
            }]},
            mission_blue={"missions": [{
                "order": 1, "instruction": "본인 web 로그 분석", "points": 10,
                "target_vm": "web",
                "verify": {"type": "output_contains", "expect": "POST"},
            }]},
            scoring={}, time_limit_sec=1800)
        s.add(scn)
        await s.flush()
        b = await bs.create_battle(
            s, scenario_id=scn.id, mode="duel", monitor="bastion",
            participants=[
                {"user_id": red_u.id, "role": "red", "infra_id": red_inf.id},
                {"user_id": blue_u.id, "role": "blue", "infra_id": blue_inf.id},
            ],
            created_by=red_u.id,
        )
        await bs.start_battle(s, b.id, actor_user_id=red_u.id)
        return b.id, red_u.id, blue_u.id


async def _events(battle_id):
    async with SessionLocal() as s:
        return (await s.scalars(
            select(BattleEvent).where(BattleEvent.battle_id == battle_id)
            .order_by(BattleEvent.id.asc()))).all()


async def _score(battle_id, role):
    async with SessionLocal() as s:
        p = await s.scalar(select(BattleParticipant).where(
            BattleParticipant.battle_id == battle_id, BattleParticipant.role == role))
        return p.score


@pytest.mark.asyncio
async def test_red_opponent_assessed_on_blue_infra(monkeypatch):
    bid, red_id, blue_id = await _make_duel(red_assess_target="opponent")
    calls = []
    monkeypatch.setattr(assessor_client, "assess", build_fake_assess(calls=calls))
    await auto_monitor.run_once(bid, tick_idx=1)

    # red 미션(opponent) + blue 미션(self) 모두 blue infra(10.0.0.2) 에서 채점 → 한 번 호출
    assessed_ips = {c["vm_ip"] for c in calls}
    assert assessed_ips == {"10.0.0.2"}

    evs = await _events(bid)
    red_ev = next((e for e in evs if e.event_type == "exploit"), None)
    assert red_ev is not None
    assert red_ev.detail["side"] == "red"
    assert red_ev.detail["assessed_infra_id"] is not None
    assert red_ev.actor_user_id == red_id      # 점수는 red 학생에게
    assert await _score(bid, "red") == 20
    assert await _score(bid, "blue") == 10      # blue 미션 self 도 채점됨


@pytest.mark.asyncio
async def test_red_self_assessed_on_own_infra(monkeypatch):
    bid, red_id, blue_id = await _make_duel(red_assess_target="self")
    calls = []
    monkeypatch.setattr(assessor_client, "assess", build_fake_assess(calls=calls))
    await auto_monitor.run_once(bid, tick_idx=1)

    # red 미션(self)=red infra(10.0.0.1), blue 미션(self)=blue infra(10.0.0.2) → 두 infra 호출
    assessed_ips = {c["vm_ip"] for c in calls}
    assert assessed_ips == {"10.0.0.1", "10.0.0.2"}
    assert await _score(bid, "red") == 20
    assert await _score(bid, "blue") == 10


@pytest.mark.asyncio
async def test_register_only_own_infra_enforced():
    """학생은 본인 infra 만 등록 가능 — 타인 user_id 로 participant 구성 시 거부."""
    async with SessionLocal() as s:
        red_u = User(email="r@x", name="R", password_hash=hash_password("pass1234"))
        blue_u = User(email="b@x", name="B", password_hash=hash_password("pass1234"))
        s.add_all([red_u, blue_u])
        await s.flush()
        # blue 의 infra
        blue_inf = Infra(owner_id=blue_u.id, name="b", vm_ip="10.0.0.2",
                         ssh_password_enc="x", bastion_api_key="k", port_map={})
        s.add(blue_inf)
        scn = Scenario(title="t", status="validated",
                       mission_red={"missions": []}, mission_blue={"missions": []},
                       scoring={}, time_limit_sec=1800)
        s.add(scn)
        await s.flush()
        # red 가 blue 의 infra 를 자기 것으로 주장 → ValueError
        with pytest.raises(ValueError):
            await bs.create_battle(
                s, scenario_id=scn.id, mode="duel", monitor="bastion",
                participants=[{"user_id": red_u.id, "role": "red", "infra_id": blue_inf.id}],
                created_by=red_u.id)
