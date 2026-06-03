"""학생 제출 → AI 시맨틱 채점(개별). 점수는 AI 가 결정(학생 claim 무시), 공정성 보장.

mock AI verdict 로 결정론 검증: pass→AI점수, fail→0, claim 무시, 미션없음 학생→0, admin 수동, 보류.
"""
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
from app.services import event_analyzer as ea  # noqa: E402


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


async def _signup(client, email, name):
    r = await client.post("/auth/signup", json={"email": email, "password": "pass12345", "name": name})
    return r.json()["access_token"], r.json()["user"]["id"]


async def _make_admin(email):
    from app.models import User
    from sqlalchemy import select
    async with SessionLocal() as s:
        u = (await s.scalars(select(User).where(User.email == email))).first()
        u.role = "admin"; await s.commit()


async def _solo_active(client, headers, uid):
    sc = (await client.get("/scenarios", headers=headers)).json()[0]["id"]
    cr = await client.post("/battles", headers=headers, json={
        "scenario_id": sc, "mode": "solo", "monitor": "bastion",
        "participants": [{"user_id": uid, "role": "solo", "infra_id": None}]})
    bid = cr.json()["battle"]["id"]
    await client.post(f"/battles/{bid}/start", headers=headers)
    # red mission #1 의 최대 점수
    det = (await client.get(f"/battles/{bid}", headers=headers)).json()
    red1 = next(m for m in det["my_missions"] if m["side"] == "red" and m["order"] == 1)
    return bid, red1["points"]


def _mock_grade(monkeypatch, *, awarded, verdict="pass"):
    async def fake_grade(*, report, mission, scenario, evidence_text="", max_points=0, **kw):
        # awarded='max' → 미션 최대점, 아니면 정수
        pts = max_points if awarded == "max" else awarded
        return ea.AnalysisResult(reasoning=f"mock {verdict}", model="mock-claude",
                                 verdict=verdict, awarded_points=pts, cost_usd=0.01)
    monkeypatch.setattr(ea, "grade", fake_grade)


@pytest.mark.asyncio
async def test_pass_awards_ai_points_not_claimed(monkeypatch):
    async with await _new() as client:
        tok, uid = await _signup(client, "alice@example.com", "Alice")
        h = {"authorization": f"Bearer {tok}"}
        bid, maxp = await _solo_active(client, h, uid)
        _mock_grade(monkeypatch, awarded="max", verdict="pass")
        # 학생이 점수 200 을 claim 해도 무시되고 AI 가 정한 maxp 부여
        ev = await client.post(f"/battles/{bid}/events", headers=h, json={
            "event_type": "exploit", "mission_order": 1, "mission_side": "red",
            "points": 200, "what_i_did": "sqlmap -u ...", "what_happened": "is vulnerable"})
        assert ev.status_code == 201
        g = ev.json()["detail"]["grading"]
        assert g["ai_decided"] is True
        assert g["awarded_points"] == maxp
        assert g["claimed_points"] == 200       # 기록은 됨
        det = (await client.get(f"/battles/{bid}", headers=h)).json()
        assert det["participants"][0]["score"] == maxp   # claim(200) 아님


@pytest.mark.asyncio
async def test_fail_verdict_awards_zero(monkeypatch):
    async with await _new() as client:
        tok, uid = await _signup(client, "alice@example.com", "Alice")
        h = {"authorization": f"Bearer {tok}"}
        bid, maxp = await _solo_active(client, h, uid)
        _mock_grade(monkeypatch, awarded=0, verdict="fail")
        ev = await client.post(f"/battles/{bid}/events", headers=h, json={
            "event_type": "exploit", "mission_order": 1, "mission_side": "red",
            "points": 100, "what_i_did": "아무것도 안 함"})
        assert ev.json()["detail"]["grading"]["awarded_points"] == 0
        det = (await client.get(f"/battles/{bid}", headers=h)).json()
        assert det["participants"][0]["score"] == 0


@pytest.mark.asyncio
async def test_award_clamped_to_mission_max(monkeypatch):
    async with await _new() as client:
        tok, uid = await _signup(client, "alice@example.com", "Alice")
        h = {"authorization": f"Bearer {tok}"}
        bid, maxp = await _solo_active(client, h, uid)
        _mock_grade(monkeypatch, awarded=9999, verdict="pass")   # AI 가 과도하게 줘도
        ev = await client.post(f"/battles/{bid}/events", headers=h, json={
            "event_type": "exploit", "mission_order": 1, "mission_side": "red", "points": 0})
        assert ev.json()["detail"]["grading"]["awarded_points"] == maxp   # 미션 최대로 clamp


@pytest.mark.asyncio
async def test_no_mission_student_gets_zero(monkeypatch):
    async with await _new() as client:
        tok, uid = await _signup(client, "alice@example.com", "Alice")
        h = {"authorization": f"Bearer {tok}"}
        bid, maxp = await _solo_active(client, h, uid)
        # 미션 미지정 + 일반 event_type → AI 채점 대상 아님 → 학생은 0
        ev = await client.post(f"/battles/{bid}/events", headers=h, json={
            "event_type": "note", "points": 50, "description": "그냥 메모"})
        assert ev.json()["detail"]["grading"]["awarded_points"] == 0
        det = (await client.get(f"/battles/{bid}", headers=h)).json()
        assert det["participants"][0]["score"] == 0


@pytest.mark.asyncio
async def test_admin_manual_points_for_non_mission(monkeypatch):
    async with await _new() as client:
        await _signup(client, "rooty@example.com", "rooty")
        await _make_admin("rooty@example.com")
        atok = (await client.post("/auth/login", json={
            "email": "rooty@example.com", "password": "pass12345"})).json()["access_token"]
        ah = {"authorization": f"Bearer {atok}"}
        tok, uid = await _signup(client, "alice@example.com", "Alice")
        h = {"authorization": f"Bearer {tok}"}
        bid, maxp = await _solo_active(client, h, uid)
        # admin 이 미션 외 수동 보정 점수 (운영 override)
        ev = await client.post(f"/battles/{bid}/events", headers=ah, json={
            "event_type": "system", "points": 7, "description": "admin 보정"})
        assert ev.json()["detail"]["grading"]["awarded_points"] == 7


@pytest.mark.asyncio
async def test_review_pending_when_ai_unavailable(monkeypatch):
    async with await _new() as client:
        tok, uid = await _signup(client, "alice@example.com", "Alice")
        h = {"authorization": f"Bearer {tok}"}
        bid, maxp = await _solo_active(client, h, uid)

        async def unavailable(*, report, mission, scenario, evidence_text="", max_points=0, **kw):
            return ea.AnalysisResult(reasoning="AI 불가 — 강사 검토", model="needs-review",
                                     verdict="review", awarded_points=None)
        monkeypatch.setattr(ea, "grade", unavailable)
        ev = await client.post(f"/battles/{bid}/events", headers=h, json={
            "event_type": "exploit", "mission_order": 1, "mission_side": "red", "points": 50})
        g = ev.json()["detail"]["grading"]
        assert g["verdict"] == "review" and g["awarded_points"] == 0   # 보류 — 자동 점수 금지
