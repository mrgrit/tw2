"""(옵션) provisioner — arm_rule 시작 무장·종료 회수, SKIP_PROVISIONER 기본 OFF=no-op."""
from __future__ import annotations
import os
import pytest
import pytest_asyncio

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("TUBEWAR_JWT_SECRET", "test-secret-32-chars-please-not-shorter")
os.environ.setdefault("TUBEWAR_FERNET_KEY", "ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg=")

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.models import Infra, Scenario, User  # noqa: E402
from app.security import hash_password  # noqa: E402
from app.services import battle_service as bs, provisioner, assessor_client  # noqa: E402


@pytest_asyncio.fixture(autouse=True)
async def _reset():
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.drop_all)


async def _battle_with_arm_rule():
    async with SessionLocal() as s:
        u = User(email="a@x", name="A", password_hash=hash_password("pass1234"))
        s.add(u); await s.flush()
        inf = Infra(owner_id=u.id, name="i", vm_ip="10.0.0.1", ssh_password_enc="x",
                    bastion_api_key="k", port_map={})
        s.add(inf)
        scn = Scenario(title="T", status="validated",
                       mission_red={"missions": [{"order": 1, "points": 10, "target_vm": "secu",
                                                   "arm_rule": {"id": "modsec-sqli", "template": "sqli"},
                                                   "verify": {"type": "output_contains", "expect": "x"}}]},
                       mission_blue={"missions": []}, scoring={}, time_limit_sec=1800)
        s.add(scn); await s.flush()
        b = await bs.create_battle(s, scenario_id=scn.id, mode="solo", monitor="bastion",
                                   participants=[{"user_id": u.id, "role": "solo", "infra_id": inf.id}],
                                   created_by=u.id)
        return b.id


@pytest.mark.asyncio
async def test_skip_default_is_noop(monkeypatch):
    monkeypatch.delenv("SKIP_PROVISIONER", raising=False)
    assert provisioner.is_skipped() is True
    bid = await _battle_with_arm_rule()
    calls = []

    async def fake_pr(infra, **kw):
        calls.append(kw); return {"ok": True}
    monkeypatch.setattr(assessor_client, "provision_rule", fake_pr)
    async with SessionLocal() as s:
        res = await provisioner.arm_battle_rules(s, bid)
    assert res["skipped"] is True
    assert calls == []   # 무장 호출 0


@pytest.mark.asyncio
async def test_enabled_arms_and_withdraws(monkeypatch):
    monkeypatch.setenv("SKIP_PROVISIONER", "0")
    assert provisioner.is_skipped() is False
    bid = await _battle_with_arm_rule()
    calls = []

    async def fake_pr(infra, *, action, rule, battle_id=None, **kw):
        calls.append(action); return {"ok": True}
    monkeypatch.setattr(assessor_client, "provision_rule", fake_pr)

    async with SessionLocal() as s:
        armed = await provisioner.arm_battle_rules(s, bid)
    assert armed["count"] == 1 and calls == ["arm"]

    async with SessionLocal() as s:
        withdrawn = await provisioner.withdraw_battle_rules(s, bid)
    assert withdrawn["count"] == 1 and calls == ["arm", "withdraw"]
