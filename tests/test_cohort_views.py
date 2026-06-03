"""cohort 서브트리 필터 — leaderboard/stats/battle 목록 + 신원-only(null) 정상 동작."""
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
        u.role = "admin"
        await s.commit()


async def _score_solo_battle(client, headers, uid, scenario_id, points, cohort_id=None):
    body = {"scenario_id": scenario_id, "mode": "solo", "monitor": "bastion",
            "participants": [{"user_id": uid, "role": "solo", "infra_id": None}]}
    if cohort_id is not None:
        body["cohort_id"] = cohort_id
    cr = await client.post("/battles", headers=headers, json=body)
    assert cr.status_code == 201, cr.text
    bid = cr.json()["battle"]["id"]
    await client.post(f"/battles/{bid}/start", headers=headers)
    await client.post(f"/battles/{bid}/events", headers=headers, json={
        "event_type": "exploit", "target": "web", "description": "win", "points": points})
    await client.post(f"/battles/{bid}/end", headers=headers)
    return bid


@pytest.mark.asyncio
async def test_cohort_subtree_filter_views_and_identity_only():
    async with await _new() as client:
        await _signup(client, "rooty@example.com", "rooty")
        await _make_admin("rooty@example.com")
        atok = (await client.post("/auth/login", json={
            "email": "rooty@example.com", "password": "pass12345"})).json()["access_token"]
        ah = {"authorization": f"Bearer {atok}"}

        a_tok, a_id = await _signup(client, "alice@example.com", "Alice")
        b_tok, b_id = await _signup(client, "bob@example.com", "Bob")
        c_tok, c_id = await _signup(client, "carol@example.com", "Carol")
        ah_a = {"authorization": f"Bearer {a_tok}"}
        ah_c = {"authorization": f"Bearer {c_tok}"}

        # cohort 트리: course3 → A분반
        course = (await client.post("/cohorts", headers=ah, json={
            "kind": "course", "name": "웹해킹", "course_ref": "course3"})).json()
        section = (await client.post("/cohorts", headers=ah, json={
            "kind": "section", "name": "A분반", "parent_id": course["id"]})).json()
        # alice, bob → A분반. carol 은 어디에도 없음(신원-only).
        await client.post(f"/cohorts/{section['id']}/members", headers=ah, json={"user_id": a_id})
        await client.post(f"/cohorts/{section['id']}/members", headers=ah, json={"user_id": b_id})

        scn = (await client.get("/scenarios", headers=ah)).json()[0]["id"]

        # alice: cohort-bound battle +20 ; carol: 신원-only battle +30
        await _score_solo_battle(client, ah_a, a_id, scn, 20, cohort_id=section["id"])
        await _score_solo_battle(client, ah_c, c_id, scn, 30, cohort_id=None)

        # ── leaderboard cohort 필터: course 서브트리 → alice 만(carol 제외) ──
        lb = (await client.get(f"/leaderboard/users?cohort_id={course['id']}", headers=ah)).json()
        names = {r["name"] for r in lb}
        assert "Alice" in names
        assert "Carol" not in names

        # ── leaderboard 무필터(신원-only 포함): carol 보임 ──
        lb_all = (await client.get("/leaderboard/users", headers=ah)).json()
        assert "Carol" in {r["name"] for r in lb_all}

        # ── admin/stats cohort 스코프 ──
        st = (await client.get(f"/admin/stats?cohort_id={course['id']}", headers=ah)).json()
        assert st["user_count"] == 2          # alice + bob (carol/admin 제외)
        assert st["battles_total"] == 1       # alice 의 cohort battle 만
        top_names = {t["name"] for t in st["top_scorers"]}
        assert "Carol" not in top_names

        # 무필터 stats — 전체
        st_all = (await client.get("/admin/stats", headers=ah)).json()
        assert st_all["battles_total"] == 2

        # ── admin/battles cohort 필터 ──
        ab = (await client.get(f"/admin/battles?cohort_id={course['id']}", headers=ah)).json()
        assert len(ab) == 1
        assert ab[0]["cohort_id"] == section["id"]

        # 무필터 — 2개(신원-only 포함)
        ab_all = (await client.get("/admin/battles", headers=ah)).json()
        assert len(ab_all) == 2


@pytest.mark.asyncio
async def test_battle_create_rejects_unknown_cohort():
    async with await _new() as client:
        a_tok, a_id = await _signup(client, "alice@example.com", "Alice")
        ah = {"authorization": f"Bearer {a_tok}"}
        scn = (await client.get("/scenarios", headers=ah)).json()[0]["id"]
        r = await client.post("/battles", headers=ah, json={
            "scenario_id": scn, "mode": "solo", "monitor": "bastion", "cohort_id": 99999,
            "participants": [{"user_id": a_id, "role": "solo", "infra_id": None}]})
        assert r.status_code == 400
        assert "cohort" in r.text
