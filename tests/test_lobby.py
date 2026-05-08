"""Phase 9.2 — admin 로비 개설 + 학생 join + 미션 노출."""
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


async def _signup(client, email, name) -> tuple[str, int, int]:
    r = await client.post("/auth/signup", json={
        "email": email, "password": "pass12345", "name": name,
    })
    tok = r.json()["access_token"]
    uid = r.json()["user"]["id"]
    h = {"authorization": f"Bearer {tok}"}
    await client.post("/infras", headers=h, json={
        "name": f"{name}-6v6", "vm_ip": "10.0.0.1",
        "ssh_user": "ccc", "ssh_password": "ccc", "bastion_api_key": "k",
    })
    inf = (await client.get("/infras", headers=h)).json()[0]["id"]
    return tok, uid, inf


async def _make_admin(client, email):
    from app.models import User
    from sqlalchemy import select
    async with SessionLocal() as s:
        u = (await s.scalars(select(User).where(User.email == email))).first()
        u.role = "admin"
        await s.commit()


@pytest.mark.asyncio
async def test_admin_creates_lobby_students_join_then_start() -> None:
    async with await _new() as client:
        # admin
        atok, _, _ = await _signup(client, "rooty@example.com", "rooty")
        await _make_admin(client, "rooty@example.com")
        atok = (await client.post("/auth/login", json={
            "email": "rooty@example.com", "password": "pass12345"})).json()["access_token"]
        ah = {"authorization": f"Bearer {atok}"}

        # 학생 2명
        a_tok, a_id, a_inf = await _signup(client, "alice@example.com", "alice")
        b_tok, b_id, b_inf = await _signup(client, "bob@example.com", "bob")
        ah_a = {"authorization": f"Bearer {a_tok}"}
        ah_b = {"authorization": f"Bearer {b_tok}"}

        sc = (await client.get("/scenarios", headers=ah)).json()[0]["id"]

        # admin 이 lobby 개설 (참가자 0명, duel)
        r = await client.post("/battles", headers=ah, json={
            "scenario_id": sc, "mode": "duel", "monitor": "bastion",
            "hint_enabled": True, "target_apps": ["juiceshop"],
            "participants": [],
        })
        assert r.status_code == 201
        bid = r.json()["battle"]["id"]
        assert r.json()["participants"] == []

        # 학생이 lobby 가 아직 시작 전인데 start 시도 → 400 (참가자 0명)
        r = await client.post(f"/battles/{bid}/start", headers=ah)
        assert r.status_code == 400
        assert "no participants" in r.json()["detail"] or "requires" in r.json()["detail"]

        # alice red 로 join
        r = await client.post(f"/battles/{bid}/join", headers=ah_a, json={
            "role": "red", "infra_id": a_inf,
        })
        assert r.status_code == 200
        assert r.json()["my_role"] == "red"

        # alice 가 같은 역할 또 join → 400 (이미 참가)
        r = await client.post(f"/battles/{bid}/join", headers=ah_a, json={
            "role": "blue", "infra_id": a_inf,
        })
        assert r.status_code == 400

        # bob 이 red 로 join → 400 (red 이미 alice)
        r = await client.post(f"/battles/{bid}/join", headers=ah_b, json={
            "role": "red", "infra_id": b_inf,
        })
        assert r.status_code == 400
        assert "already taken" in r.json()["detail"]

        # bob 이 blue 로 join → 200
        r = await client.post(f"/battles/{bid}/join", headers=ah_b, json={
            "role": "blue", "infra_id": b_inf,
        })
        assert r.status_code == 200
        assert len(r.json()["participants"]) == 2

        # 이제 시작 가능
        r = await client.post(f"/battles/{bid}/start", headers=ah_a)
        assert r.status_code == 200
        assert r.json()["battle"]["status"] == "active"


@pytest.mark.asyncio
async def test_missions_visible_per_role() -> None:
    """red 학생은 red 미션, blue 학생은 blue 미션만 my_missions 에."""
    async with await _new() as client:
        atok, _, _ = await _signup(client, "rooty@example.com", "rooty")
        await _make_admin(client, "rooty@example.com")
        atok = (await client.post("/auth/login", json={
            "email": "rooty@example.com", "password": "pass12345"})).json()["access_token"]
        ah = {"authorization": f"Bearer {atok}"}
        a_tok, a_id, a_inf = await _signup(client, "alice@example.com", "alice")
        b_tok, b_id, b_inf = await _signup(client, "bob@example.com", "bob")
        ah_a = {"authorization": f"Bearer {a_tok}"}
        ah_b = {"authorization": f"Bearer {b_tok}"}

        sc = (await client.get("/scenarios", headers=ah)).json()[0]["id"]
        bid = (await client.post("/battles", headers=ah, json={
            "scenario_id": sc, "mode": "duel", "monitor": "bastion",
            "participants": [],
        })).json()["battle"]["id"]

        await client.post(f"/battles/{bid}/join", headers=ah_a, json={
            "role": "red", "infra_id": a_inf})
        await client.post(f"/battles/{bid}/join", headers=ah_b, json={
            "role": "blue", "infra_id": b_inf})

        # alice (red) 시점
        d_a = (await client.get(f"/battles/{bid}", headers=ah_a)).json()
        assert d_a["my_role"] == "red"
        assert all(m["side"] == "red" for m in d_a["my_missions"])
        assert all(m["side"] == "blue" for m in d_a["opponent_missions"])
        assert len(d_a["my_missions"]) > 0
        first = d_a["my_missions"][0]
        assert "instruction" in first and first["instruction"]
        assert "order" in first

        # bob (blue) 시점
        d_b = (await client.get(f"/battles/{bid}", headers=ah_b)).json()
        assert d_b["my_role"] == "blue"
        assert all(m["side"] == "blue" for m in d_b["my_missions"])
        assert all(m["side"] == "red" for m in d_b["opponent_missions"])

        # 관전자 (admin 외 비참가자)
        c_tok, _, _ = await _signup(client, "spec@example.com", "spec")
        ah_c = {"authorization": f"Bearer {c_tok}"}
        d_c = (await client.get(f"/battles/{bid}", headers=ah_c)).json()
        assert d_c["my_role"] is None
        assert len(d_c["my_missions"]) == 0
        # 관전자에게는 양쪽 모두 opponent_missions 에 노출
        sides = {m["side"] for m in d_c["opponent_missions"]}
        assert sides == {"red", "blue"}


@pytest.mark.asyncio
async def test_leave_lobby_then_battle_full_again() -> None:
    async with await _new() as client:
        atok, _, _ = await _signup(client, "rooty@example.com", "rooty")
        await _make_admin(client, "rooty@example.com")
        atok = (await client.post("/auth/login", json={
            "email": "rooty@example.com", "password": "pass12345"})).json()["access_token"]
        ah = {"authorization": f"Bearer {atok}"}
        a_tok, _, a_inf = await _signup(client, "a@example.com", "a")
        b_tok, _, b_inf = await _signup(client, "b@example.com", "b")
        ah_a = {"authorization": f"Bearer {a_tok}"}
        ah_b = {"authorization": f"Bearer {b_tok}"}

        sc = (await client.get("/scenarios", headers=ah)).json()[0]["id"]
        bid = (await client.post("/battles", headers=ah, json={
            "scenario_id": sc, "mode": "duel", "monitor": "bastion",
            "participants": [],
        })).json()["battle"]["id"]

        await client.post(f"/battles/{bid}/join", headers=ah_a, json={"role": "red", "infra_id": a_inf})
        await client.post(f"/battles/{bid}/join", headers=ah_b, json={"role": "blue", "infra_id": b_inf})
        # alice leaves
        r = await client.post(f"/battles/{bid}/leave", headers=ah_a)
        assert r.status_code == 200
        assert len(r.json()["participants"]) == 1
        # alice rejoin red
        r = await client.post(f"/battles/{bid}/join", headers=ah_a, json={"role": "red", "infra_id": a_inf})
        assert r.status_code == 200


@pytest.mark.asyncio
async def test_solo_still_requires_self() -> None:
    """solo 모드는 lobby 불가 — 본인 강제."""
    async with await _new() as client:
        a_tok, a_id, a_inf = await _signup(client, "u@example.com", "u")
        ah = {"authorization": f"Bearer {a_tok}"}
        sc = (await client.get("/scenarios", headers=ah)).json()[0]["id"]
        # 본인 빈 → 400
        r = await client.post("/battles", headers=ah, json={
            "scenario_id": sc, "mode": "solo", "monitor": "bastion",
            "participants": [],
        })
        assert r.status_code == 400
        # 본인 포함 → 201
        r = await client.post("/battles", headers=ah, json={
            "scenario_id": sc, "mode": "solo", "monitor": "bastion",
            "participants": [{"user_id": a_id, "role": "solo", "infra_id": a_inf}],
        })
        assert r.status_code == 201
