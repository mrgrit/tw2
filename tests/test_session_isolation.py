"""세션/캐시 격리 — 사용자별 데이터가 다른 계정에 새지 않음 + API 응답 no-store.

회귀 방지: 한 사용자가 등록한 인프라가 다른 사용자 응답/캐시로 노출되던 문제(cross-user 누수).
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
from app.db import Base, engine  # noqa: E402


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
    return r.json()["access_token"]


@pytest.mark.asyncio
async def test_api_responses_are_no_store():
    async with await _new() as client:
        tok = await _signup(client, "blue@example.com", "블루팀")
        r = await client.get("/infras", headers={"authorization": f"Bearer {tok}"})
        assert r.status_code == 200
        cc = r.headers.get("cache-control", "")
        assert "no-store" in cc, f"cache-control no-store 누락: {cc!r}"
        assert r.headers.get("vary", "").lower().find("authorization") >= 0


@pytest.mark.asyncio
async def test_user_b_never_sees_user_a_infra():
    async with await _new() as client:
        blue = await _signup(client, "blue@example.com", "블루팀")
        red = await _signup(client, "red@example.com", "레드팀")
        # 블루팀이 인프라 등록
        r = await client.post("/infras", headers={"authorization": f"Bearer {blue}"}, json={
            "name": "blue-6v6", "vm_ip": "192.168.0.80", "ssh_user": "ccc",
            "ssh_password": "1", "bastion_api_key": "ccc-api-key-2026"})
        assert r.status_code == 200
        # 블루팀 본인은 1개
        assert len((await client.get("/infras", headers={"authorization": f"Bearer {blue}"})).json()) == 1
        # 레드팀은 0개 — 블루팀 인프라가 절대 안 보여야
        red_list = (await client.get("/infras", headers={"authorization": f"Bearer {red}"})).json()
        assert red_list == [], f"레드팀에게 다른 계정 인프라 노출됨: {red_list}"
