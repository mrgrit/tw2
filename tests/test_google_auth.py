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


def test_google_verify_transport_importable():
    """_verify 는 아래 테스트들에서 monkeypatch 되므로, 실제 검증 경로의 의존성 누락을 여기서 잡는다.
    (google-auth 만 설치되고 requests 가 없으면 진짜 토큰이 전부 401 로 거부된다.)"""
    from google.auth.transport import requests as g_requests
    from google.oauth2 import id_token  # noqa: F401

    assert callable(g_requests.Request())


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
async def test_google_domain_restriction_allows_org_account(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "google_client_id", "test-client")
    monkeypatch.setattr(s, "google_allowed_domain", "ync.ac.kr")
    claims = dict(FAKE, email="dave@ync.ac.kr", hd="ync.ac.kr")
    monkeypatch.setattr(google_auth, "_verify", lambda cred, cid: dict(claims))
    async with _client() as c:
        r = await c.post("/auth/google", json={"credential": "tok" * 10})
    assert r.status_code == 200, r.text
    assert r.json()["user"]["email"] == "dave@ync.ac.kr"


@pytest.mark.asyncio
@pytest.mark.parametrize("claims", [
    # 조직 메일 주소로 만든 '개인' 구글 계정 — hd 없음
    dict(FAKE, email="eve@ync.ac.kr"),
    # 타 조직 Workspace 계정
    dict(FAKE, email="eve@other.ac.kr", hd="other.ac.kr"),
    # hd 는 맞지만 이메일이 다른 도메인(보조 도메인/별칭)
    dict(FAKE, email="eve@other.ac.kr", hd="ync.ac.kr"),
])
async def test_google_domain_restriction_requires_hd_and_email(monkeypatch, claims):
    s = get_settings()
    monkeypatch.setattr(s, "google_client_id", "test-client")
    monkeypatch.setattr(s, "google_allowed_domain", "ync.ac.kr")
    monkeypatch.setattr(google_auth, "_verify", lambda cred, cid: dict(claims))
    async with _client() as c:
        r = await c.post("/auth/google", json={"credential": "tok" * 10})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_google_unverified_email_rejected(monkeypatch):
    monkeypatch.setattr(get_settings(), "google_client_id", "test-client")
    claims = {k: v for k, v in FAKE.items() if k != "email_verified"}
    monkeypatch.setattr(google_auth, "_verify", lambda cred, cid: dict(claims))
    async with _client() as c:
        r = await c.post("/auth/google", json={"credential": "tok" * 10})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_password_auth_disabled_closes_password_endpoints(monkeypatch):
    """구글 전용 모드 — 가입/로그인/비밀번호 변경은 403, 구글 로그인은 그대로."""
    s = get_settings()
    monkeypatch.setattr(s, "google_client_id", "test-client")
    monkeypatch.setattr(google_auth, "_verify", lambda cred, cid: dict(FAKE))
    async with _client() as c:
        # 전환 전에 만들어진 로컬 계정
        su = await c.post("/auth/signup", json={
            "email": "frank@example.com", "password": "frankpass123", "name": "Frank",
        })
        assert su.status_code == 200

        monkeypatch.setattr(s, "password_auth", False)
        p = await c.get("/auth/providers")
        assert p.json()["password"]["enabled"] is False

        r = await c.post("/auth/signup", json={
            "email": "grace@example.com", "password": "gracepass123", "name": "Grace",
        })
        assert r.status_code == 403
        r = await c.post("/auth/login", json={
            "email": "frank@example.com", "password": "frankpass123",
        })
        assert r.status_code == 403

        g = await c.post("/auth/google", json={"credential": "tok" * 10})
        assert g.status_code == 200, g.text
        r = await c.post(
            "/auth/me/password",
            headers={"authorization": f"Bearer {g.json()['access_token']}"},
            json={"current_password": "whatever1", "new_password": "whatever2"},
        )
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_google_no_provision_rejects_unknown(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "google_client_id", "test-client")
    monkeypatch.setattr(s, "google_auto_provision", False)
    monkeypatch.setattr(google_auth, "_verify", lambda cred, cid: dict(FAKE))
    async with _client() as c:
        r = await c.post("/auth/google", json={"credential": "tok" * 10})
    assert r.status_code == 403  # 미등록 + 자동가입 off → 거부
