"""게스트 계정 — 관리자 등록 ID/비밀번호. 구글 전용 모드(TUBEWAR_PASSWORD_AUTH=0)에서도 로그인 허용.

정책: signup 은 닫힌 채로, auth_provider=guest 계정만 비밀번호 로그인/변경 가능.
게스트는 admin 승격 불가, 비밀번호 재설정은 게스트에게만.
"""
from __future__ import annotations
import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("TUBEWAR_JWT_SECRET", "test-secret-32-chars-please-not-shorter")

from app.main import app  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.models import User  # noqa: E402


@pytest_asyncio.fixture(autouse=True)
async def _tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _admin_headers(c: AsyncClient) -> dict:
    r = await c.post("/auth/signup", json={
        "email": "boss@example.com", "password": "bosspass123", "name": "Boss",
    })
    assert r.status_code == 200
    async with SessionLocal() as s:
        u = (await s.scalars(select(User).where(User.email == "boss@example.com"))).first()
        u.role = "admin"
        await s.commit()
    return {"authorization": f"Bearer {r.json()['access_token']}"}


GUEST = {"login_id": "Guest01", "name": "손님", "password": "guestpass123"}


@pytest.mark.asyncio
async def test_guest_logs_in_when_password_auth_disabled(monkeypatch):
    async with _client() as c:
        ah = await _admin_headers(c)
        # 전환 전 로컬 학생(비게스트)
        st = await c.post("/auth/signup", json={
            "email": "stu@example.com", "password": "stupass123", "name": "Stu",
        })
        assert st.status_code == 200

        r = await c.post("/admin/users/guests", headers=ah, json=GUEST)
        assert r.status_code == 201, r.text
        g = r.json()
        assert g["email"] == "guest01"          # 소문자 정규화
        assert g["auth_provider"] == "guest"
        assert g["role"] == "student"

        monkeypatch.setattr(get_settings(), "password_auth", False)

        # 게스트: 로그인 OK (ID 대소문자 무관)
        lg = await c.post("/auth/login", json={"email": "GUEST01", "password": "guestpass123"})
        assert lg.status_code == 200, lg.text
        assert lg.json()["user"]["auth_provider"] == "guest"
        gh = {"authorization": f"Bearer {lg.json()['access_token']}"}

        # 게스트 비밀번호 틀림 → 401
        bad = await c.post("/auth/login", json={"email": "guest01", "password": "wrongpass123"})
        assert bad.status_code == 401
        # 비게스트 로컬 계정 → 403(구글로 안내)
        loc = await c.post("/auth/login", json={"email": "stu@example.com", "password": "stupass123"})
        assert loc.status_code == 403
        # 존재하지 않는 ID → 401(존재 여부 노출 안 함)
        nope = await c.post("/auth/login", json={"email": "nobody", "password": "whatever123"})
        assert nope.status_code == 401
        # signup 은 여전히 닫힘
        su = await c.post("/auth/signup", json={
            "email": "new@example.com", "password": "newpass123", "name": "New",
        })
        assert su.status_code == 403

        # 게스트는 자기 비밀번호 변경 가능, 이후 새 비밀번호로 로그인
        ch = await c.post("/auth/me/password", headers=gh,
                          json={"current_password": "guestpass123", "new_password": "newguest456"})
        assert ch.status_code == 200, ch.text
        again = await c.post("/auth/login", json={"email": "guest01", "password": "newguest456"})
        assert again.status_code == 200


@pytest.mark.asyncio
async def test_guest_admin_endpoints_policy():
    async with _client() as c:
        ah = await _admin_headers(c)
        r = await c.post("/admin/users/guests", headers=ah, json=GUEST)
        assert r.status_code == 201
        gid = r.json()["id"]

        # 중복 ID → 409
        dup = await c.post("/admin/users/guests", headers=ah, json=GUEST)
        assert dup.status_code == 409
        # 형식 위반(@, 공백, 짧음) → 422
        for bad_id in ["a@b.com", "has space", "ab", "한글"]:
            bad = await c.post("/admin/users/guests", headers=ah, json={**GUEST, "login_id": bad_id})
            assert bad.status_code == 422, bad_id

        # 게스트 → admin 승격 금지
        pr = await c.patch(f"/admin/users/{gid}", headers=ah, json={"role": "admin"})
        assert pr.status_code == 400
        # 비활성화는 가능
        off = await c.patch(f"/admin/users/{gid}", headers=ah, json={"is_active": False})
        assert off.status_code == 200 and off.json()["is_active"] is False
        dis = await c.post("/auth/login", json={"email": "guest01", "password": "guestpass123"})
        assert dis.status_code == 403  # account disabled

        # 비밀번호 재설정: 게스트 OK
        on = await c.patch(f"/admin/users/{gid}", headers=ah, json={"is_active": True})
        assert on.status_code == 200
        rs = await c.post(f"/admin/users/{gid}/password", headers=ah, json={"password": "resetpass789"})
        assert rs.status_code == 200, rs.text
        lg = await c.post("/auth/login", json={"email": "guest01", "password": "resetpass789"})
        assert lg.status_code == 200
        # 비게스트(관리자 자신=local)에게는 거부
        me = await c.get("/auth/me", headers=ah)
        no = await c.post(f"/admin/users/{me.json()['id']}/password", headers=ah, json={"password": "resetpass789"})
        assert no.status_code == 400

        # 목록에 auth_provider 노출
        lst = await c.get("/admin/users", headers=ah)
        assert {u["email"]: u["auth_provider"] for u in lst.json()} == {
            "boss@example.com": "local", "guest01": "guest",
        }


@pytest.mark.asyncio
async def test_guest_endpoints_require_admin():
    async with _client() as c:
        r = await c.post("/auth/signup", json={
            "email": "stu@example.com", "password": "stupass123", "name": "Stu",
        })
        sh = {"authorization": f"Bearer {r.json()['access_token']}"}
        assert (await c.post("/admin/users/guests", headers=sh, json=GUEST)).status_code == 403
        assert (await c.post("/admin/users/1/password", headers=sh, json={"password": "xxxxxxxx1"})).status_code == 403
