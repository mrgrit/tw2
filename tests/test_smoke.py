"""Phase 1 의 가장 얇은 테스트 — 라우터 등록 + health check.

DB 는 in-memory aiosqlite 로 override (postgres 없이도 CI 가능).
"""
from __future__ import annotations
import os
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("TUBEWAR_JWT_SECRET", "test-secret-32-chars-please-not-shorter")

# import 는 환경변수 설정 후
from app.main import app  # noqa: E402
from app.db import Base, engine  # noqa: E402


@pytest_asyncio.fixture(autouse=True)
async def _create_tables():
    """매 테스트마다 in-memory sqlite 테이블 새로 생성 (lifespan 우회)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.mark.asyncio
async def test_health() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["service"] == "tubewar-api"


@pytest.mark.asyncio
async def test_signup_login_cycle() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # signup
        r = await client.post("/auth/signup", json={
            "email": "alice@example.com", "password": "alicepass123", "name": "Alice",
        })
        assert r.status_code == 200, r.text
        token = r.json()["access_token"]

        # me
        r2 = await client.get("/auth/me", headers={"authorization": f"Bearer {token}"})
        assert r2.status_code == 200
        assert r2.json()["email"] == "alice@example.com"

        # login
        r3 = await client.post("/auth/login", json={
            "email": "alice@example.com", "password": "alicepass123",
        })
        assert r3.status_code == 200
        assert r3.json()["user"]["role"] == "student"
