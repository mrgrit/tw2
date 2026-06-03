"""admin 인프라 관리 — 전체 목록(소유자 포함), smoke, assess-check, 삭제, 권한, cohort 필터."""
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
from app.services import assessor_client  # noqa: E402


@pytest_asyncio.fixture(autouse=True)
async def _reset():
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)
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


async def _register_infra(client, headers, name, vm_ip):
    await client.post("/infras", headers=headers, json={
        "name": name, "vm_ip": vm_ip, "ssh_user": "ccc", "ssh_password": "1",
        "bastion_api_key": "ccc-api-key-2026"})


@pytest_asyncio.fixture
async def setup(_reset):
    async with await _new() as client:
        await _signup(client, "rooty@example.com", "rooty")
        await _make_admin("rooty@example.com")
        atok = (await client.post("/auth/login", json={
            "email": "rooty@example.com", "password": "pass12345"})).json()["access_token"]
        ah = {"authorization": f"Bearer {atok}"}
        a_tok, a_id = await _signup(client, "alice@example.com", "Alice")
        b_tok, b_id = await _signup(client, "bob@example.com", "Bob")
        await _register_infra(client, {"authorization": f"Bearer {a_tok}"}, "alice-6v6", "10.0.0.1")
        await _register_infra(client, {"authorization": f"Bearer {b_tok}"}, "bob-6v6", "10.0.0.2")
        yield client, ah, a_tok, a_id, b_id


@pytest.mark.asyncio
async def test_admin_lists_all_infras_with_owner(setup):
    client, ah, a_tok, a_id, b_id = setup
    r = await client.get("/admin/infras", headers=ah)
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 2
    by_ip = {x["vm_ip"]: x for x in rows}
    assert by_ip["10.0.0.1"]["owner_name"] == "Alice"
    assert by_ip["10.0.0.2"]["owner_email"] == "bob@example.com"
    # ssh 평문 비밀은 노출 안 됨
    assert "ssh_password" not in rows[0]
    # owner 필터
    r2 = await client.get(f"/admin/infras?owner_id={a_id}", headers=ah)
    assert len(r2.json()) == 1 and r2.json()[0]["owner_id"] == a_id


@pytest.mark.asyncio
async def test_student_cannot_list_admin_infras(setup):
    client, ah, a_tok, a_id, b_id = setup
    r = await client.get("/admin/infras", headers={"authorization": f"Bearer {a_tok}"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_admin_smoke_updates_status(setup):
    client, ah, a_tok, a_id, b_id = setup
    inf_id = (await client.get(f"/admin/infras?owner_id={a_id}", headers=ah)).json()[0]["id"]
    r = await client.post(f"/admin/infras/{inf_id}/smoke", headers=ah)
    assert r.status_code == 200
    assert "ok" in r.json() and "checks" in r.json()      # SmokeResult
    # vm_ip 가짜라 degraded 예상, 상태 갱신 확인
    row = (await client.get(f"/admin/infras?owner_id={a_id}", headers=ah)).json()[0]
    assert row["status"] in ("healthy", "degraded")
    assert row["last_smoke_at"] is not None


@pytest.mark.asyncio
async def test_admin_assess_check(setup, monkeypatch):
    client, ah, a_tok, a_id, b_id = setup
    inf_id = (await client.get(f"/admin/infras?owner_id={a_id}", headers=ah)).json()[0]["id"]

    async def fake_assess(infra, checks, **kw):
        return {"ok": True, "results": [{"id": "ping", "passed": True, "evidence": "ok /etc/passwd"}]}

    async def fake_activity(infra, **kw):
        return {"ok": True, "commands": [], "fim": [], "alerts": [], "services": {"apache": "up"}}

    monkeypatch.setattr(assessor_client, "assess", fake_assess)
    monkeypatch.setattr(assessor_client, "activity", fake_activity)
    r = await client.post(f"/admin/infras/{inf_id}/assess-check", headers=ah)
    assert r.status_code == 200
    body = r.json()
    assert body["assessor_ok"] is True and body["bastion_ok"] is True
    assert "etc/passwd" in (body["evidence"] or "")


@pytest.mark.asyncio
async def test_admin_delete_infra(setup):
    client, ah, a_tok, a_id, b_id = setup
    inf_id = (await client.get(f"/admin/infras?owner_id={a_id}", headers=ah)).json()[0]["id"]
    d = await client.delete(f"/admin/infras/{inf_id}", headers=ah)
    assert d.status_code == 204
    assert len((await client.get("/admin/infras", headers=ah)).json()) == 1


@pytest.mark.asyncio
async def test_admin_infra_cohort_filter(setup):
    client, ah, a_tok, a_id, b_id = setup
    # alice 만 코호트에 배치 → cohort 필터 시 alice infra 만
    sec = (await client.post("/cohorts", headers=ah, json={"kind": "section", "name": "A"})).json()
    await client.post(f"/cohorts/{sec['id']}/members", headers=ah, json={"user_id": a_id})
    rows = (await client.get(f"/admin/infras?cohort_id={sec['id']}", headers=ah)).json()
    assert len(rows) == 1 and rows[0]["owner_id"] == a_id
