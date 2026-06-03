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
from app.services import event_analyzer as ea  # noqa: E402


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
async def test_heartbeat_collapse_in_place() -> None:
    """auto_monitor 의 heartbeat 가 변화 없을 때 1 row 로 collapse 되는지."""
    from app.services.auto_monitor import _emit_heartbeat
    async with await _new() as client:
        tok, uid, inf = await _signup(client, "hb@example.com", "hb")
        h = {"authorization": f"Bearer {tok}"}
        sc = (await client.get("/scenarios", headers=h)).json()[0]["id"]
        bid = (await client.post("/battles", headers=h, json={
            "scenario_id": sc, "mode": "solo", "monitor": "bastion",
            "participants": [{"user_id": uid, "role": "solo", "infra_id": inf}],
        })).json()["battle"]["id"]
        await client.post(f"/battles/{bid}/start", headers=h)

        # 3번 heartbeat 직접 호출 — collapse 되어야
        async with SessionLocal() as s:
            await _emit_heartbeat(s, battle_id=bid, monitor_mode="bastion",
                                  infras_count=1, target_apps=["juiceshop"], tick_idx=4)
        async with SessionLocal() as s:
            await _emit_heartbeat(s, battle_id=bid, monitor_mode="bastion",
                                  infras_count=1, target_apps=["juiceshop"], tick_idx=8)
        async with SessionLocal() as s:
            await _emit_heartbeat(s, battle_id=bid, monitor_mode="bastion",
                                  infras_count=1, target_apps=["juiceshop"], tick_idx=12)

        body = (await client.get(f"/battles/{bid}", headers=h)).json()
        hb = [e for e in body["events"]
              if e["event_type"] == "system" and e["target"] == "monitor"
              and (e.get("detail") or {}).get("kind") == "heartbeat_range"]
        # collapse → row 1개만, ticks=3
        assert len(hb) == 1
        assert hb[0]["detail"]["ticks"] == 3
        assert hb[0]["reasoning"] and "무변화 구간" in hb[0]["reasoning"]
        assert "~" in hb[0]["description"]

        # 점수 이벤트 끼면 다음 heartbeat 부터 새 row
        await client.post(f"/battles/{bid}/events", headers=h, json={
            "event_type": "exploit", "target": "juiceshop", "description": "x",
            "points": 5, "detail": {},
        })
        async with SessionLocal() as s:
            await _emit_heartbeat(s, battle_id=bid, monitor_mode="bastion",
                                  infras_count=1, target_apps=["juiceshop"], tick_idx=16)
        body = (await client.get(f"/battles/{bid}", headers=h)).json()
        hb2 = [e for e in body["events"]
               if e["event_type"] == "system" and e["target"] == "monitor"
               and (e.get("detail") or {}).get("kind") == "heartbeat_range"]
        assert len(hb2) == 2  # 점수 이벤트 후 새 heartbeat row
        assert hb2[1]["detail"]["ticks"] == 1


@pytest.mark.asyncio
async def test_event_reasoning_field_roundtrip(monkeypatch) -> None:
    """이벤트 보고 시 채점 분석 자동 생성 — mission_order 유무로 두 모드:

    (a) mission_order 없음 → 일반 안내 reasoning + raw detail 에 report 보존
    (b) mission_order 있음 → success_criteria 비교 분석 (criteria_met/missing 산출)
    """
    async with await _new() as client:
        tok, uid, inf = await _signup(client, "u@example.com", "u")
        h = {"authorization": f"Bearer {tok}"}
        sc = (await client.get("/scenarios", headers=h)).json()[0]["id"]

        bid = (await client.post("/battles", headers=h, json={
            "scenario_id": sc, "mode": "solo", "monitor": "bastion",
            "participants": [{"user_id": uid, "role": "solo", "infra_id": inf}],
        })).json()["battle"]["id"]
        await client.post(f"/battles/{bid}/start", headers=h)

        # (a) mission_order 미입력 — AI 채점 대상 아님(학생 0점) + 미연결 안내 reasoning
        await client.post(f"/battles/{bid}/events", headers=h, json={
            "event_type": "exploit", "target": "juiceshop",
            "description": "SQLi 시도", "points": 20,
        })
        body = (await client.get(f"/battles/{bid}", headers=h)).json()
        e_a = next(e for e in body["events"] if e["event_type"] == "exploit")
        assert e_a["reasoning"] and "특정 미션과 연결되지 않" in e_a["reasoning"]
        assert e_a["detail"]["report"]["mission_order"] is None
        g_a = e_a["detail"]["grading"]
        assert g_a["ai_decided"] is False and g_a["awarded_points"] == 0   # 학생 self-점수 무시

        # (b) mission_order 지정 → AI 시맨틱 채점 경로 (점수는 AI 결정). AI 를 mock.
        from app.models import Scenario
        async with SessionLocal() as s:
            scn = await s.get(Scenario, sc)
            red_missions = (scn.mission_red or {}).get("missions") or []
            target_mission = next((m for m in red_missions
                                   if (m.get("verify") or {}).get("semantic", {}).get("success_criteria")), None)
        assert target_mission, "테스트 시나리오에 success_criteria 있는 red 미션 없음"
        crits = target_mission["verify"]["semantic"]["success_criteria"]

        async def fake_grade(*, report, mission, scenario, evidence_text="", max_points=0, **kw):
            return ea.AnalysisResult(
                reasoning=f"**AI 채점** 미션 #{mission.order} — 모든 기준 충족 ✅",
                model="mock-claude", verdict="pass", awarded_points=max_points,
                criteria_met=list(crits), criteria_missing=[])
        monkeypatch.setattr(ea, "grade", fake_grade)

        await client.post(f"/battles/{bid}/events", headers=h, json={
            "event_type": "exploit",
            "target": target_mission.get("target_vm") or "attacker",
            "description": f"미션 #{target_mission['order']} 시도",
            "points": 200,   # claim — 무시됨
            "mission_order": target_mission["order"], "mission_side": "red",
            "what_i_did": "\n".join(crits),
            "what_happened": "실행 완료",
        })
        body = (await client.get(f"/battles/{bid}", headers=h)).json()
        scored = [e for e in body["events"]
                  if e.get("detail", {}).get("report", {}).get("mission_order") == target_mission["order"]]
        assert scored, f"mission #{target_mission['order']} 보고가 events 에 없음"
        e_b = scored[-1]
        rs = e_b["reasoning"]
        assert rs and "AI 채점" in rs and f"미션 #{target_mission['order']}" in rs
        g_b = e_b["detail"]["grading"]
        assert g_b["ai_decided"] is True and g_b["verdict"] == "pass"
        assert g_b["criteria_met"] == crits and g_b["criteria_missing"] == []
        assert g_b["awarded_points"] == target_mission.get("points", 0)   # AI=미션최대, claim(200) 아님
