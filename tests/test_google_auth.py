"""구글 로그인 — 검증/매핑/정책 테스트.

실제 구글 인증서 검증(google_auth._verify)은 monkeypatch 로 대체(네트워크 불필요).
GIS 흐름의 백엔드 측(자동가입·재로그인·기존계정연결·도메인제한·비활성)을 검증한다.
"""
from __future__ import annotations
import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("TUBEWAR_JWT_SECRET", "test-secret-32-chars-please-not-shorter")

from app.main import app  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import Base, engine  # noqa: E402
from app.services import google_auth  # noqa: E402


@pytest_asyncio.fixture(autouse=True)
async def _tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


FAKE = {
    "iss": "https://accounts.google.com",
    "sub": "11223344556677889900",
    "email": "bob@example.com",
    "email_verified": True,
    "name": "Bob Kim",
}


@pytest.mark.asyncio
async def test_providers_reflects_config(monkeypatch):
    monkeypatch.setattr(get_settings(), "google_client_id", "")
    async with _client() as c:
        r = await c.get("/auth/providers")
    assert r.status_code == 200
    assert r.json()["google"]["enabled"] is False


@pytest.mark.asyncio
async def test_google_disabled_returns_503(monkeypatch):
    monkeypatch.setattr(get_settings(), "google_client_id", "")
    async with _client() as c:
        r = await c.post("/auth/google", json={"credential": "x" * 20})
    assert r.status_code == 503


@pytest.mark.asyncio
async def test_google_auto_provision_then_relogin(monkeypatch):
    monkeypatch.setattr(get_settings(), "google_client_id", "test.apps.googleusercontent.com")
    monkeypatch.setattr(google_auth, "_verify", lambda cred, cid: dict(FAKE))
    async with _client() as c:
        r = await c.post("/auth/google", json={"credential": "tok" * 10})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["user"]["email"] == "bob@example.com"
        assert body["user"]["role"] == "student"
        tok = body["access_token"]

        me = await c.get("/auth/me", headers={"authorization": f"Bearer {tok}"})
        assert me.status_code == 200
        assert me.json()["email"] == "bob@example.com"

        # 같은 sub 재로그인 → 동일 계정(중복 생성 안 됨)
        r2 = await c.post("/auth/google", json={"credential": "tok" * 10})
        assert r2.status_code == 200
        assert r2.json()["user"]["id"] == body["user"]["id"]


@pytest.mark.asyncio
async def test_google_links_existing_local_account(monkeypatch):
    monkeypatch.setattr(get_settings(), "google_client_id", "test-client")
    async with _client() as c:
        s = await c.post("/auth/signup", json={
            "email": "carol@example.com", "password": "carolpass123", "name": "Carol",
        })
        assert s.status_code == 200
        local_id = s.json()["user"]["id"]

        claims = dict(FAKE, sub="99887766", email="carol@example.com", name="Carol G")
        monkeypatch.setattr(google_auth, "_verify", lambda cred, cid: dict(claims))
        g = await c.post("/auth/google", json={"credential": "tok" * 10})
        assert g.status_code == 200, g.text
        # 새 계정이 아니라 기존 로컬 계정에 연결
        assert g.json()["user"]["id"] == local_id

        # 로컬 비밀번호 로그인도 여전히 동작
        lg = await c.post("/auth/login", json={
            "email": "carol@example.com", "password": "carolpass123",
        })
        assert lg.status_code == 200


@pytest.mark.asyncio
async def test_google_domain_restriction_blocks(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "google_client_id", "test-client")
    monkeypatch.setattr(s, "google_allowed_domain", "ync.ac.kr")
    monkeypatch.setattr(google_auth, "_verify", lambda cred, cid: dict(FAKE))  # bob@example.com
    async with _client() as c:
        r = await c.post("/auth/google", json={"credential": "tok" * 10})
    assert r.status_code == 401  # 도메인 불일치 → 검증 단계에서 거부


@pytest.mark.asyncio
async def test_google_no_provision_rejects_unknown(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "google_client_id", "test-client")
    monkeypatch.setattr(s, "google_auto_provision", False)
    monkeypatch.setattr(google_auth, "_verify", lambda cred, cid: dict(FAKE))
    async with _client() as c:
        r = await c.post("/auth/google", json={"credential": "tok" * 10})
    assert r.status_code == 403  # 미등록 + 자동가입 off → 거부
