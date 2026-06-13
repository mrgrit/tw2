"""Phase 2 — 시나리오 import + solo battle e2e + 권한 체크."""
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
from app.services.scenario_loader import import_scenarios  # noqa: E402
from app.services import event_analyzer as ea  # noqa: E402


def _mock_ai_pass(monkeypatch):
    """AI 채점을 결정론 mock 으로 — 미션 최대점 부여(pass)."""
    async def fake_grade(*, report, mission, scenario, evidence_text="", max_points=0, **kw):
        return ea.AnalysisResult(reasoning="mock pass", model="mock-claude",
                                 verdict="pass", awarded_points=max_points, cost_usd=0.0)
    monkeypatch.setattr(ea, "grade", fake_grade)


@pytest_asyncio.fixture(autouse=True)
async def _reset_db():
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)
    # 시나리오 자동 import (lifespan 우회)
    async with SessionLocal() as s:
        await import_scenarios(s)
    yield
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.drop_all)


async def _signup(client: AsyncClient, email: str, name: str) -> str:
    r = await client.post("/auth/signup", json={"email": email, "password": "pass1234", "name": name})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


async def _new_client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_scenario_import_and_listing() -> None:
    async with await _new_client() as client:
        token = await _signup(client, "alice@example.com", "Alice")
        h = {"authorization": f"Bearer {token}"}
        r = await client.get("/scenarios", headers=h)
    assert r.status_code == 200
    body = r.json()
    # 17 시나리오가 있어야 (championship 포함)
    assert len(body) >= 17, f"expected >=17 scenarios, got {len(body)}"
    titles = {s["title"] for s in body}
    assert any("WAF" in t for t in titles), f"sqli-vs-waf scenario missing in {titles}"


@pytest.mark.asyncio
async def test_solo_battle_full_lifecycle(monkeypatch) -> None:
    _mock_ai_pass(monkeypatch)
    async with await _new_client() as client:
        token = await _signup(client, "alice@example.com", "Alice")
        h = {"authorization": f"Bearer {token}"}

        # 1) 인프라 등록
        ir = await client.post("/infras", headers=h, json={
            "name": "alice-6v6", "vm_ip": "10.0.0.1",
            "ssh_user": "ccc", "ssh_password": "ccc",
            "bastion_api_key": "test-key",
        })
        assert ir.status_code == 200, ir.text
        infra_id = ir.json()["id"]

        # 2) 시나리오 1개 선택
        sr = await client.get("/scenarios", headers=h)
        scenario_id = sr.json()[0]["id"]

        # 3) solo battle 생성
        me = (await client.get("/auth/me", headers=h)).json()
        cr = await client.post("/battles", headers=h, json={
            "scenario_id": scenario_id,
            "mode": "solo",
            "monitor": "bastion",
            "participants": [{"user_id": me["id"], "role": "solo", "infra_id": infra_id}],
        })
        assert cr.status_code == 201, cr.text
        battle_id = cr.json()["battle"]["id"]
        assert cr.json()["battle"]["status"] == "pending"

        # 4) 시작
        st = await client.post(f"/battles/{battle_id}/start", headers=h)
        assert st.status_code == 200, st.text
        assert st.json()["battle"]["status"] == "active"

        # 미션 #1(red) 최대 점수 확인
        det0 = (await client.get(f"/battles/{battle_id}", headers=h)).json()
        red1 = next(m for m in det0["my_missions"] if m["side"] == "red" and m["order"] == 1)
        maxp = red1["points"]

        # 5) 학생 제출 → AI 채점(mock pass) → 점수는 AI 가 결정(학생 claim 무시)
        ev = await client.post(f"/battles/{battle_id}/events", headers=h, json={
            "event_type": "exploit", "target": "web", "description": "SQLi success",
            "mission_order": 1, "mission_side": "red",
            "what_i_did": "sqlmap -u ... --batch", "what_happened": "is vulnerable", "points": 200,
        })
        assert ev.status_code == 201, ev.text
        assert ev.json()["grade_status"] == "graded"        # 동기 채점 완료(StudentSubmissionOut)
        assert ev.json()["awarded_points"] == maxp          # claim(200) 아님

        # 6) detail 확인 — AI 점수 반영
        det = await client.get(f"/battles/{battle_id}", headers=h)
        assert det.status_code == 200
        body = det.json()
        assert body["participants"][0]["score"] == maxp
        # system 2개 (created+started) + exploit 1 = 3 이벤트
        assert len(body["events"]) >= 3

        # 7) 종료
        end = await client.post(f"/battles/{battle_id}/end", headers=h)
        assert end.status_code == 200
        assert end.json()["battle"]["status"] == "completed"


@pytest.mark.asyncio
async def test_duel_permission_denies_outsider() -> None:
    async with await _new_client() as client:
        ta = await _signup(client, "alice@example.com", "Alice")
        tb = await _signup(client, "bob@example.com", "Bob")
        tc = await _signup(client, "carol@example.com", "Carol")
        ha = {"authorization": f"Bearer {ta}"}
        hb = {"authorization": f"Bearer {tb}"}
        hc = {"authorization": f"Bearer {tc}"}

        # alice + bob 인프라
        ir_a = await client.post("/infras", headers=ha, json={
            "name": "a", "vm_ip": "10.0.0.1", "ssh_user": "ccc",
            "ssh_password": "ccc", "bastion_api_key": "k",
        })
        ir_b = await client.post("/infras", headers=hb, json={
            "name": "b", "vm_ip": "10.0.0.2", "ssh_user": "ccc",
            "ssh_password": "ccc", "bastion_api_key": "k",
        })
        a_id = (await client.get("/auth/me", headers=ha)).json()["id"]
        b_id = (await client.get("/auth/me", headers=hb)).json()["id"]
        infra_a = ir_a.json()["id"]
        infra_b = ir_b.json()["id"]

        scenario_id = (await client.get("/scenarios", headers=ha)).json()[0]["id"]

        # carol 이 alice/bob duel 만들려고 시도 → 403 (자기 자신 미포함)
        cr = await client.post("/battles", headers=hc, json={
            "scenario_id": scenario_id,
            "mode": "duel",
            "monitor": "bastion",
            "participants": [
                {"user_id": a_id, "role": "red", "infra_id": infra_a},
                {"user_id": b_id, "role": "blue", "infra_id": infra_b},
            ],
        })
        assert cr.status_code == 403, cr.text


@pytest.mark.asyncio
async def test_solo_validation_rejects_two_participants() -> None:
    async with await _new_client() as client:
        token = await _signup(client, "alice@example.com", "Alice")
        h = {"authorization": f"Bearer {token}"}
        scenario_id = (await client.get("/scenarios", headers=h)).json()[0]["id"]
        me = (await client.get("/auth/me", headers=h)).json()["id"]
        r = await client.post("/battles", headers=h, json={
            "scenario_id": scenario_id, "mode": "solo", "monitor": "bastion",
            "participants": [
                {"user_id": me, "role": "solo", "infra_id": None},
                {"user_id": me, "role": "solo", "infra_id": None},
            ],
        })
        assert r.status_code == 400
        assert "solo mode" in r.text or "duplicate" in r.text


@pytest.mark.asyncio
async def test_infra_password_encrypted_at_rest() -> None:
    """등록한 ssh_password 가 DB 에 평문으로 저장되지 않음을 확인."""
    from app.models import Infra
    from sqlalchemy import select
    async with await _new_client() as client:
        token = await _signup(client, "alice@example.com", "Alice")
        h = {"authorization": f"Bearer {token}"}
        await client.post("/infras", headers=h, json={
            "name": "a", "vm_ip": "10.0.0.1",
            "ssh_user": "ccc", "ssh_password": "supersecret",
            "bastion_api_key": "k",
        })
    async with SessionLocal() as s:
        i = (await s.scalars(select(Infra))).first()
        assert i is not None
        assert "supersecret" not in i.ssh_password_enc
        assert i.ssh_password_enc.startswith("fernet:")
