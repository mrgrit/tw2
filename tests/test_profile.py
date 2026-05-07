"""Phase 8.5 — 프로필 (이름·비번 변경) 단위 테스트."""
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


@pytest_asyncio.fixture(autouse=True)
async def _reset(monkeypatch):
    monkeypatch.setenv("TUBEWAR_RATE_LIMIT_DISABLE", "1")
    rl.reset()
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.drop_all)


async def _new() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_change_password_happy_path() -> None:
    async with await _new() as client:
        r = await client.post("/auth/signup", json={
            "email": "u@example.com", "password": "oldpass1234", "name": "U",
        })
        h = {"authorization": f"Bearer {r.json()['access_token']}"}

        r = await client.post("/auth/me/password", headers=h, json={
            "current_password": "oldpass1234", "new_password": "newpass5678",
        })
        assert r.status_code == 200
        assert r.json() == {"ok": True}

        # 이전 비번 거부
        bad = await client.post("/auth/login", json={
            "email": "u@example.com", "password": "oldpass1234",
        })
        assert bad.status_code == 401
        # 새 비번 통과
        ok = await client.post("/auth/login", json={
            "email": "u@example.com", "password": "newpass5678",
        })
        assert ok.status_code == 200


@pytest.mark.asyncio
async def test_change_password_wrong_current_rejected() -> None:
    async with await _new() as client:
        r = await client.post("/auth/signup", json={
            "email": "v@example.com", "password": "alpha1234", "name": "V",
        })
        h = {"authorization": f"Bearer {r.json()['access_token']}"}
        r = await client.post("/auth/me/password", headers=h, json={
            "current_password": "WRONG", "new_password": "beta12345",
        })
        assert r.status_code == 400
        # 비번 안 바뀜
        ok = await client.post("/auth/login", json={
            "email": "v@example.com", "password": "alpha1234",
        })
        assert ok.status_code == 200


@pytest.mark.asyncio
async def test_change_password_must_differ() -> None:
    async with await _new() as client:
        r = await client.post("/auth/signup", json={
            "email": "w@example.com", "password": "samepass1", "name": "W",
        })
        h = {"authorization": f"Bearer {r.json()['access_token']}"}
        r = await client.post("/auth/me/password", headers=h, json={
            "current_password": "samepass1", "new_password": "samepass1",
        })
        assert r.status_code == 400


@pytest.mark.asyncio
async def test_update_profile_name() -> None:
    async with await _new() as client:
        r = await client.post("/auth/signup", json={
            "email": "n@example.com", "password": "pass12345", "name": "OldName",
        })
        h = {"authorization": f"Bearer {r.json()['access_token']}"}
        r = await client.patch("/auth/me", headers=h, json={"name": "NewName"})
        assert r.status_code == 200
        assert r.json()["name"] == "NewName"
        # /me 도 갱신
        me = await client.get("/auth/me", headers=h)
        assert me.json()["name"] == "NewName"
