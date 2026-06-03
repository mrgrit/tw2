"""채점 AI 프로필 — 등록/수정/기본/삭제/권한, 시나리오 선택·해석, provider(CC/Bastion) 분기."""
from __future__ import annotations
import os
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("TUBEWAR_JWT_SECRET", "test-secret-32-chars-please-not-shorter")
os.environ.setdefault("TUBEWAR_FERNET_KEY", "ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg=")

from app.main import app  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.services.scenario_loader import import_scenarios  # noqa: E402
from app.services import graders, event_analyzer as ea  # noqa: E402


@pytest_asyncio.fixture(autouse=True)
async def _reset():
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)
    async with SessionLocal() as s:
        await import_scenarios(s)
    yield
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.drop_all)


async def _new() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _admin(client):
    await client.post("/auth/signup", json={"email": "rooty@example.com", "password": "pass12345", "name": "r"})
    from app.models import User
    from sqlalchemy import select
    async with SessionLocal() as s:
        u = (await s.scalars(select(User).where(User.email == "rooty@example.com"))).first()
        u.role = "admin"; await s.commit()
    tok = (await client.post("/auth/login", json={"email": "rooty@example.com", "password": "pass12345"})).json()["access_token"]
    return {"authorization": f"Bearer {tok}"}


@pytest.mark.asyncio
async def test_grader_crud_and_default_and_secrets():
    async with await _new() as client:
        ah = await _admin(client)
        # CC 프로필
        r = await client.post("/admin/graders", headers=ah, json={
            "name": "CC-haiku", "provider": "cc", "model": "claude-haiku-4-5", "is_default": True})
        assert r.status_code == 201
        cc_id = r.json()["id"]
        assert r.json()["is_default"] is True and r.json()["has_api_key"] is False

        # bastion 은 base_url 필수
        bad = await client.post("/admin/graders", headers=ah, json={
            "name": "no-url", "provider": "bastion", "model": "gpt-oss:120b"})
        assert bad.status_code == 400

        r2 = await client.post("/admin/graders", headers=ah, json={
            "name": "Bastion-gptoss", "provider": "bastion", "model": "gpt-oss:120b",
            "base_url": "http://10.0.0.80:9100", "api_key": "secret-key", "is_default": True})
        assert r2.status_code == 201
        bid = r2.json()["id"]
        # api_key 비노출
        assert "api_key" not in r2.json() and r2.json()["has_api_key"] is True

        # 기본은 하나만 — bastion 을 default 로 만들면 CC 는 해제
        lst = (await client.get("/admin/graders", headers=ah)).json()
        defaults = [g for g in lst if g["is_default"]]
        assert len(defaults) == 1 and defaults[0]["id"] == bid

        # 수정
        pa = await client.patch(f"/admin/graders/{cc_id}", headers=ah, json={"model": "claude-opus-4-8"})
        assert pa.json()["model"] == "claude-opus-4-8"

        # 삭제
        d = await client.delete(f"/admin/graders/{bid}", headers=ah)
        assert d.status_code == 204


@pytest.mark.asyncio
async def test_grader_admin_only():
    async with await _new() as client:
        st = await client.post("/auth/signup", json={"email": "s@example.com", "password": "pass12345", "name": "s"})
        sh = {"authorization": f"Bearer {st.json()['access_token']}"}
        assert (await client.get("/admin/graders", headers=sh)).status_code == 403
        assert (await client.post("/admin/graders", headers=sh, json={
            "name": "x", "provider": "cc", "model": "m"})).status_code == 403


@pytest.mark.asyncio
async def test_scenario_grader_selection_and_resolve():
    async with await _new() as client:
        ah = await _admin(client)
        gid = (await client.post("/admin/graders", headers=ah, json={
            "name": "Bastion", "provider": "bastion", "model": "gpt-oss:120b",
            "base_url": "http://10.0.0.80:9100", "api_key": "k"})).json()["id"]
        sc = (await client.get("/scenarios", headers=ah)).json()[0]["id"]
        # 시나리오에 채점기 선택
        r = await client.patch(f"/admin/scenarios/{sc}", headers=ah, json={"grader_profile_id": gid})
        assert r.status_code == 200 and r.json()["grader_profile_id"] == gid
        # 해석
        from app.models import Scenario
        async with SessionLocal() as s:
            scn = await s.get(Scenario, sc)
            g = await graders.resolve_for_scenario(s, scn)
        assert g["provider"] == "bastion" and g["model"] == "gpt-oss:120b"
        assert g["base_url"] == "http://10.0.0.80:9100"
        # 해제(0) → 기본 없음 → CC fallback
        await client.patch(f"/admin/scenarios/{sc}", headers=ah, json={"grader_profile_id": 0})
        async with SessionLocal() as s:
            scn = await s.get(Scenario, sc)
            g2 = await graders.resolve_for_scenario(s, scn)
        assert g2["provider"] == "cc"   # fallback


@pytest.mark.asyncio
async def test_grade_dispatch_bastion(monkeypatch):
    called = {}

    async def fake_bastion(payload, base_url, model, api_key):
        called["url"] = base_url; called["model"] = model
        return ('{"passed":true,"awarded_points":7,"verdict":"pass",'
                '"criteria_met":[],"criteria_missing":[],"reasoning":"bastion ok"}'), 0.0

    async def fake_claude(payload, model=None):
        called["claude"] = True
        return '{"passed":true,"awarded_points":3,"verdict":"pass","reasoning":"cc"}', 0.5

    monkeypatch.setattr(ea, "_bastion_grade", fake_bastion)
    monkeypatch.setattr(ea, "_claude_grade", fake_claude)
    mission = ea.MissionContext(side="blue", order=1, instruction="x", target_vm="web",
                                points=10, hint=None, verify_expect=None, semantic_intent=None)
    report = ea.StudentReport(user_name="u", event_type="detect", target="web",
                              points_claimed=0, description="", what_i_did="did it")
    res = await ea.grade(report=report, mission=mission, scenario=None, max_points=10,
                         grader={"provider": "bastion", "model": "gpt-oss:120b",
                                 "base_url": "http://x:9100", "api_key": "k"})
    assert called.get("model") == "gpt-oss:120b" and "claude" not in called
    assert res.awarded_points == 7 and res.model == "bastion:gpt-oss:120b"


@pytest.mark.asyncio
async def test_grade_dispatch_cc(monkeypatch):
    called = {}

    async def fake_claude(payload, model=None):
        called["model"] = model
        return '{"passed":true,"awarded_points":5,"verdict":"pass","reasoning":"cc"}', 0.1

    monkeypatch.setattr(ea, "_claude_grade", fake_claude)
    mission = ea.MissionContext(side="red", order=1, instruction="x", target_vm="attacker",
                                points=20, hint=None, verify_expect=None, semantic_intent=None)
    report = ea.StudentReport(user_name="u", event_type="exploit", target="a",
                              points_claimed=0, description="", what_i_did="sqlmap")
    res = await ea.grade(report=report, mission=mission, scenario=None, max_points=20,
                         grader={"provider": "cc", "model": "claude-opus-4-8"})
    assert called.get("model") == "claude-opus-4-8"
    assert res.awarded_points == 5 and res.model == "cc:claude-opus-4-8"
