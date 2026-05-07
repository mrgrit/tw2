"""Phase 7 — admin dashboard 엔드포인트 단위 테스트."""
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


async def _signup_admin(client: AsyncClient) -> str:
    """첫 사용자를 admin 으로 만들기 위해 직접 DB 조작."""
    r = await client.post("/auth/signup", json={
        "email": "rooty@example.com", "password": "rootpass123", "name": "rooty",
    })
    assert r.status_code == 200
    tok = r.json()["access_token"]
    # 승격
    from app.models import User
    from sqlalchemy import select
    async with SessionLocal() as s:
        u = (await s.scalars(select(User).where(User.email == "rooty@example.com"))).first()
        u.role = "admin"
        await s.commit()
    return tok


@pytest.mark.asyncio
async def test_admin_stats_and_battle_management() -> None:
    async with await _new() as client:
        atok = await _signup_admin(client)
        ah = {"authorization": f"Bearer {atok}"}

        # student 1명 + 그가 만든 battle
        st = await client.post("/auth/signup", json={
            "email": "bob@example.com", "password": "bobpass1234", "name": "Bob",
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
        assert cr.status_code == 201
        bid = cr.json()["battle"]["id"]

        # admin stats
        s = await client.get("/admin/stats", headers=ah)
        assert s.status_code == 200
        body = s.json()
        assert body["user_count"] >= 2
        assert body["scenario_total"] >= 17
        assert body["battles_total"] >= 1

        # admin list battles
        ab = await client.get("/admin/battles", headers=ah)
        assert ab.status_code == 200
        assert any(b["id"] == bid for b in ab.json())

        # student 가 force-end 시도 → 403
        rj = await client.post(f"/admin/battles/{bid}/force-end", headers=bh)
        assert rj.status_code == 403

        # admin force-end
        fe = await client.post(f"/admin/battles/{bid}/force-end", headers=ah)
        assert fe.status_code == 200
        assert fe.json()["status"] == "cancelled"

        # admin delete
        de = await client.delete(f"/admin/battles/{bid}", headers=ah)
        assert de.status_code == 204


@pytest.mark.asyncio
async def test_admin_user_self_demote_rejected() -> None:
    async with await _new() as client:
        atok = await _signup_admin(client)
        ah = {"authorization": f"Bearer {atok}"}
        me = (await client.get("/auth/me", headers=ah)).json()
        # 자기 자신 demote
        r = await client.patch(f"/admin/users/{me['id']}", headers=ah,
                               json={"role": "student"})
        assert r.status_code == 400
        # 자기 자신 비활성화
        r2 = await client.patch(f"/admin/users/{me['id']}", headers=ah,
                                json={"is_active": False})
        assert r2.status_code == 400


@pytest.mark.asyncio
async def test_admin_scenario_archive_and_delete() -> None:
    async with await _new() as client:
        atok = await _signup_admin(client)
        ah = {"authorization": f"Bearer {atok}"}
        sc = (await client.get("/scenarios", headers=ah)).json()[0]["id"]

        # archive
        r = await client.patch(f"/admin/scenarios/{sc}", headers=ah,
                               json={"status": "archived"})
        assert r.status_code == 200
        assert r.json()["status"] == "archived"

        # 학생이 list 했을 때 archived 시나리오는 안 보여야
        st = await client.post("/auth/signup", json={
            "email": "bob@example.com", "password": "bobpass1234", "name": "Bob",
        })
        bh = {"authorization": f"Bearer {st.json()['access_token']}"}
        slist = (await client.get("/scenarios", headers=bh)).json()
        assert all(s["id"] != sc for s in slist), "archived 시나리오가 학생 목록에 노출됨"

        # delete
        d = await client.delete(f"/admin/scenarios/{sc}", headers=ah)
        assert d.status_code == 204
