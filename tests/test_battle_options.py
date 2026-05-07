"""Phase 9 — battle 옵션 (target_apps / hint_enabled / monitor) + 힌트 + 관전."""
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


async def _signup(client: AsyncClient, email: str, name: str) -> tuple[str, int, int]:
    r = await client.post("/auth/signup", json={
        "email": email, "password": "pass12345", "name": name,
    })
    assert r.status_code == 200
    tok = r.json()["access_token"]
    uid = r.json()["user"]["id"]
    h = {"authorization": f"Bearer {tok}"}
    await client.post("/infras", headers=h, json={
        "name": f"{name}-6v6", "vm_ip": "10.0.0.1",
        "ssh_user": "ccc", "ssh_password": "ccc", "bastion_api_key": "k",
    })
    inf = (await client.get("/infras", headers=h)).json()[0]["id"]
    return tok, uid, inf


@pytest.mark.asyncio
async def test_target_apps_validation_and_random() -> None:
    async with await _new() as client:
        tok, uid, inf = await _signup(client, "a@example.com", "alice")
        h = {"authorization": f"Bearer {tok}"}
        sc = (await client.get("/scenarios", headers=h)).json()[0]["id"]

        # 잘못된 app id → 400
        r = await client.post("/battles", headers=h, json={
            "scenario_id": sc, "mode": "solo", "monitor": "bastion",
            "target_apps": ["bogus"],
            "participants": [{"user_id": uid, "role": "solo", "infra_id": inf}],
        })
        assert r.status_code == 400
        assert "unknown target_apps" in r.json()["detail"]

        # 6개 → 400
        r = await client.post("/battles", headers=h, json={
            "scenario_id": sc, "mode": "solo", "monitor": "bastion",
            "target_apps": ["juiceshop", "dvwa", "neobank", "mediforum", "govportal", "web"],
            "participants": [{"user_id": uid, "role": "solo", "infra_id": inf}],
        })
        assert r.status_code == 400

        # 정상 3개
        r = await client.post("/battles", headers=h, json={
            "scenario_id": sc, "mode": "solo", "monitor": "bastion",
            "target_apps": ["juiceshop", "dvwa", "neobank"],
            "hint_enabled": True,
            "participants": [{"user_id": uid, "role": "solo", "infra_id": inf}],
        })
        assert r.status_code == 201
        b = r.json()["battle"]
        assert sorted(b["target_apps"]) == ["dvwa", "juiceshop", "neobank"]
        assert b["hint_enabled"] is True

        # random → 서버가 2~4 자동 선택
        r = await client.post("/battles", headers=h, json={
            "scenario_id": sc, "mode": "solo", "monitor": "claude",
            "target_apps": ["random"],
            "participants": [{"user_id": uid, "role": "solo", "infra_id": inf}],
        })
        assert r.status_code == 201
        b = r.json()["battle"]
        assert 2 <= len(b["target_apps"]) <= 4
        assert "random" not in b["target_apps"]
        assert b["monitor"] == "claude"


@pytest.mark.asyncio
async def test_hint_disabled_rejected_and_cooldown() -> None:
    async with await _new() as client:
        tok, uid, inf = await _signup(client, "h@example.com", "hinter")
        h = {"authorization": f"Bearer {tok}"}
        sc = (await client.get("/scenarios", headers=h)).json()[0]["id"]

        # hint_enabled=False
        bid = (await client.post("/battles", headers=h, json={
            "scenario_id": sc, "mode": "solo", "monitor": "bastion",
            "hint_enabled": False,
            "participants": [{"user_id": uid, "role": "solo", "infra_id": inf}],
        })).json()["battle"]["id"]
        await client.post(f"/battles/{bid}/start", headers=h)

        r = await client.post(f"/battles/{bid}/hint", headers=h, json={"mission_side": "any"})
        assert r.status_code == 400
        assert "hint disabled" in r.json()["detail"]

        # hint_enabled=True 새 battle
        bid2 = (await client.post("/battles", headers=h, json={
            "scenario_id": sc, "mode": "solo", "monitor": "bastion",
            "hint_enabled": True,
            "participants": [{"user_id": uid, "role": "solo", "infra_id": inf}],
        })).json()["battle"]["id"]
        await client.post(f"/battles/{bid2}/start", headers=h)

        r = await client.post(f"/battles/{bid2}/hint", headers=h, json={"mission_side": "any"})
        assert r.status_code == 200
        body = r.json()
        assert body["text"]
        assert body["model"].startswith("bastion")  # LLM 미호출
        assert body["cache_hit"] is False
        assert body["cost_usd"] == 0.0

        # 즉시 재요청 → 429 cooldown
        r = await client.post(f"/battles/{bid2}/hint", headers=h, json={"mission_side": "any"})
        assert r.status_code == 429


@pytest.mark.asyncio
async def test_spectator_can_view_but_cannot_post_event() -> None:
    async with await _new() as client:
        a_tok, a_id, a_inf = await _signup(client, "owner@example.com", "owner")
        b_tok, b_id, b_inf = await _signup(client, "watcher@example.com", "watcher")
        ah = {"authorization": f"Bearer {a_tok}"}
        bh = {"authorization": f"Bearer {b_tok}"}
        sc = (await client.get("/scenarios", headers=ah)).json()[0]["id"]

        bid = (await client.post("/battles", headers=ah, json={
            "scenario_id": sc, "mode": "solo", "monitor": "bastion",
            "participants": [{"user_id": a_id, "role": "solo", "infra_id": a_inf}],
        })).json()["battle"]["id"]
        await client.post(f"/battles/{bid}/start", headers=ah)

        # watcher 가 detail 열람 → 200
        r = await client.get(f"/battles/{bid}", headers=bh)
        assert r.status_code == 200
        body = r.json()
        assert body["battle"]["mode"] == "solo"

        # watcher 가 이벤트 push 시도 → 403
        r = await client.post(f"/battles/{bid}/events", headers=bh, json={
            "event_type": "attack", "target": "x", "description": "spy",
            "points": 5, "detail": {},
        })
        assert r.status_code == 403

        # watcher 가 힌트 요청 → 403
        r = await client.post(f"/battles/{bid}/hint", headers=bh, json={"mission_side": "any"})
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_event_reasoning_field_roundtrip() -> None:
    """배틀 이벤트에 reasoning 이 직렬화되어 나오는지 (manual event 는 None)."""
    async with await _new() as client:
        tok, uid, inf = await _signup(client, "u@example.com", "u")
        h = {"authorization": f"Bearer {tok}"}
        sc = (await client.get("/scenarios", headers=h)).json()[0]["id"]

        bid = (await client.post("/battles", headers=h, json={
            "scenario_id": sc, "mode": "solo", "monitor": "bastion",
            "participants": [{"user_id": uid, "role": "solo", "infra_id": inf}],
        })).json()["battle"]["id"]
        await client.post(f"/battles/{bid}/start", headers=h)
        await client.post(f"/battles/{bid}/events", headers=h, json={
            "event_type": "attack", "target": "x", "description": "manual",
            "points": 10, "detail": {},
        })
        body = (await client.get(f"/battles/{bid}", headers=h)).json()
        attack_events = [e for e in body["events"] if e["event_type"] == "attack"]
        assert attack_events
        assert attack_events[0]["reasoning"] is None  # 수동 이벤트는 reasoning 없음
