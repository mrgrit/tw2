"""Phase 8 — 감사 로그 단위 테스트."""
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
from app.services import rate_limit as rl  # noqa: E402
from app.services.scenario_loader import import_scenarios  # noqa: E402


@pytest_asyncio.fixture(autouse=True)
async def _reset(monkeypatch):
    # 본 파일은 rate-limit 우회. test_rate_limit 와 모듈 import 순서가 섞여도 안전하도록
    # 매 테스트 fixture 시점에 env 를 강제 설정.
    monkeypatch.setenv("TUBEWAR_RATE_LIMIT_DISABLE", "1")
    rl.reset()
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)
    async with SessionLocal() as s:
        await import_scenarios(s)
    yield
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.drop_all)


async def _new() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _signup_admin(client: AsyncClient) -> str:
    r = await client.post("/auth/signup", json={
        "email": "rooty@example.com", "password": "rootpass123", "name": "rooty",
    })
    assert r.status_code == 200
    tok = r.json()["access_token"]
    from app.models import User
    from sqlalchemy import select
    async with SessionLocal() as s:
        u = (await s.scalars(select(User).where(User.email == "rooty@example.com"))).first()
        u.role = "admin"
        await s.commit()
    return tok


@pytest.mark.asyncio
async def test_audit_records_signup_login_and_admin_action() -> None:
    async with await _new() as client:
        atok = await _signup_admin(client)
        ah = {"authorization": f"Bearer {atok}"}

        # 학생 회원가입 (audit: auth.signup)
        st = await client.post("/auth/signup", json={
            "email": "alice@example.com", "password": "alicepass1", "name": "Alice",
        })
        assert st.status_code == 200
        # 학생 로그인 (audit: auth.login)
        lg = await client.post("/auth/login", json={
            "email": "alice@example.com", "password": "alicepass1",
        })
        assert lg.status_code == 200
        # 학생 로그인 실패 (audit: auth.login_fail)
        lf = await client.post("/auth/login", json={
            "email": "alice@example.com", "password": "wrongpass",
        })
        assert lf.status_code == 401

        # admin audit list — 위 3 종 + admin signup 까지 모두 기록되어야
        r = await client.get("/admin/audit?limit=50", headers=ah)
        assert r.status_code == 200
        actions = {row["action"] for row in r.json()}
        assert "auth.signup" in actions
        assert "auth.login" in actions
        assert "auth.login_fail" in actions

        # 학생은 audit 못 봄
        bh = {"authorization": f"Bearer {lg.json()['access_token']}"}
        r2 = await client.get("/admin/audit", headers=bh)
        assert r2.status_code == 403


@pytest.mark.asyncio
async def test_audit_filter_by_action_prefix() -> None:
    async with await _new() as client:
        atok = await _signup_admin(client)
        ah = {"authorization": f"Bearer {atok}"}

        # 시나리오 archive → scenario.patch 기록
        scn = (await client.get("/scenarios", headers=ah)).json()[0]
        r = await client.patch(f"/admin/scenarios/{scn['id']}", headers=ah,
                               json={"status": "archived"})
        assert r.status_code == 200

        r2 = await client.get("/admin/audit?action_prefix=scenario.", headers=ah)
        assert r2.status_code == 200
        actions = [row["action"] for row in r2.json()]
        assert "scenario.patch" in actions
        # 다른 prefix 는 제외되어야
        assert all(a.startswith("scenario.") for a in actions)


@pytest.mark.asyncio
async def test_audit_captures_ip_and_actor() -> None:
    async with await _new() as client:
        atok = await _signup_admin(client)
        ah = {"authorization": f"Bearer {atok}",
              "x-forwarded-for": "203.0.113.42, 10.0.0.1"}

        # admin 행동 1건 (force-end 시도용 battle 만들기)
        st = await client.post("/auth/signup", json={
            "email": "bob@example.com", "password": "bobpass123", "name": "Bob",
        })
        bh = {"authorization": f"Bearer {st.json()['access_token']}"}
        bob_id = st.json()["user"]["id"]
        await client.post("/infras", headers=bh, json={
            "name": "bob-6v6", "vm_ip": "10.0.0.2",
            "ssh_user": "ccc", "ssh_password": "ccc", "bastion_api_key": "k",
        })
        bob_inf = (await client.get("/infras", headers=bh)).json()[0]["id"]
        sc = (await client.get("/scenarios", headers=bh)).json()[0]["id"]
        cr = await client.post("/battles", headers=bh, json={
            "scenario_id": sc, "mode": "solo", "monitor": "bastion",
            "participants": [{"user_id": bob_id, "role": "solo", "infra_id": bob_inf}],
        })
        bid = cr.json()["battle"]["id"]

        # admin 이 force-end (X-Forwarded-For 가 ip 로 잡혀야)
        r = await client.post(f"/admin/battles/{bid}/force-end", headers=ah)
        assert r.status_code == 200

        rows = (await client.get("/admin/audit?action_prefix=battle.", headers=ah)).json()
        force_rows = [r for r in rows if r["action"] == "battle.force_end"]
        assert force_rows, "battle.force_end audit not recorded"
        ev = force_rows[0]
        assert ev["actor_email"] == "rooty@example.com"
        assert ev["ip"] == "203.0.113.42"   # X-Forwarded-For 의 첫 항목
        assert ev["target_id"] == str(bid)
