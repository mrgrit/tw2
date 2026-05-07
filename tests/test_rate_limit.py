"""Phase 8 — auth rate-limit 단위 테스트."""
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
    # 본 파일은 limiter 활성화 상태로 측정 — 매 테스트 시작에 env 강제 해제 + bucket clear
    monkeypatch.delenv("TUBEWAR_RATE_LIMIT_DISABLE", raising=False)
    rl.reset()
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.drop_all)


async def _new() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_signup_rate_limit_per_ip() -> None:
    """signup 5/5분 — 6번째는 429."""
    async with await _new() as client:
        ip = {"x-forwarded-for": "10.10.10.10"}
        for i in range(5):
            r = await client.post("/auth/signup", headers=ip, json={
                "email": f"u{i}@example.com", "password": "passwordok1",
                "name": f"u{i}",
            })
            assert r.status_code == 200, f"#{i} unexpected: {r.text}"
        r = await client.post("/auth/signup", headers=ip, json={
            "email": "u6@example.com", "password": "passwordok1", "name": "u6",
        })
        assert r.status_code == 429
        assert "Retry-After" in r.headers


@pytest.mark.asyncio
async def test_login_rate_limit_per_email() -> None:
    """login per-email 5/5분 — 같은 이메일 6번째는 429 (IP 와 무관하게)."""
    async with await _new() as client:
        await client.post("/auth/signup", json={
            "email": "victim@example.com", "password": "victimpass1",
            "name": "victim",
        })
        # 다른 IP 5개에서 같은 이메일로 wrong password
        for i in range(5):
            r = await client.post("/auth/login",
                                  headers={"x-forwarded-for": f"10.0.{i}.1"},
                                  json={"email": "victim@example.com",
                                        "password": "wrongpass"})
            assert r.status_code == 401, f"#{i} expected 401: {r.text}"
        # 6번째 IP — per-email bucket 이 막아야
        r = await client.post("/auth/login",
                              headers={"x-forwarded-for": "10.0.99.1"},
                              json={"email": "victim@example.com",
                                    "password": "wrongpass"})
        assert r.status_code == 429
        body = r.json()
        assert "email" in str(body).lower()


@pytest.mark.asyncio
async def test_signup_buckets_isolated_by_ip() -> None:
    """다른 IP 는 별도 bucket — A 가 막혀도 B 는 살아 있어야."""
    async with await _new() as client:
        a = {"x-forwarded-for": "10.20.30.1"}
        b = {"x-forwarded-for": "10.20.30.2"}
        for i in range(5):
            r = await client.post("/auth/signup", headers=a, json={
                "email": f"a{i}@example.com", "password": "passwordok1",
                "name": f"a{i}",
            })
            assert r.status_code == 200
        # A 막힘
        r = await client.post("/auth/signup", headers=a, json={
            "email": "a6@example.com", "password": "passwordok1", "name": "a6",
        })
        assert r.status_code == 429
        # B 는 정상
        r = await client.post("/auth/signup", headers=b, json={
            "email": "b1@example.com", "password": "passwordok1", "name": "b1",
        })
        assert r.status_code == 200
