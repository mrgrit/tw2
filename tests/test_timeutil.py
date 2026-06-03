"""시각 표준화 — 저장 UTC, 표시 KST(UTC+9). + /health 가 서울 시각 노출."""
from __future__ import annotations
import datetime as dt
import os
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("TUBEWAR_JWT_SECRET", "test-secret-32-chars-please-not-shorter")
os.environ.setdefault("TUBEWAR_FERNET_KEY", "ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg=")

from app import timeutil  # noqa: E402
from app.main import app  # noqa: E402
from app.db import Base, engine  # noqa: E402


def test_seoul_is_utc_plus_9():
    assert timeutil.SEOUL.utcoffset(None) == dt.timedelta(hours=9)


def test_to_seoul_converts_utc():
    utc = dt.datetime(2026, 6, 3, 10, 12, 7, tzinfo=dt.timezone.utc)
    kst = timeutil.to_seoul(utc)
    assert kst.hour == 19 and kst.minute == 12      # 10:12 UTC → 19:12 KST
    assert kst.utcoffset() == dt.timedelta(hours=9)


def test_naive_treated_as_utc():
    naive = dt.datetime(2026, 6, 3, 0, 0, 0)         # sqlite 류 naive → UTC 간주
    assert timeutil.to_seoul(naive).hour == 9        # 00:00 UTC → 09:00 KST


def test_iso_kst_offset_and_fmt():
    utc = dt.datetime(2026, 6, 3, 10, 12, 7, tzinfo=dt.timezone.utc)
    assert timeutil.iso_kst(utc).endswith("+09:00")
    assert timeutil.fmt_kst(utc) == "2026-06-03 19:12:07 KST"
    assert timeutil.fmt_korean(utc) == "오후 7시 12분"


def test_now_is_utc():
    assert timeutil.now().tzinfo == dt.timezone.utc


@pytest_asyncio.fixture
async def _db():
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.drop_all)


@pytest.mark.asyncio
async def test_health_exposes_seoul_time(_db):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/health")
    body = r.json()
    assert body["tz"] == "Asia/Seoul"
    assert body["server_time_kst"].endswith("+09:00")
    assert "server_time_utc" in body
