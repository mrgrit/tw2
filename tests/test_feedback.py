"""feedback — 생성(mock CC), 트리거 3종(병목/종료/수동), 저장·전달, 근거 포함·정답 미제공, 권한."""
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
from app.models import ActivityEvent, ProgressSnapshot, StudentFeedback, User  # noqa: E402
from app.security import hash_password  # noqa: E402
from app.services import feedback as fb_svc  # noqa: E402


@pytest_asyncio.fixture(autouse=True)
async def _reset(monkeypatch):
    # CC 호출을 mock — 근거 인용 + 정답 통째 미제공 형식
    async def fake_cc(payload):
        prog = payload.get("progress", {})
        return (f"## 피드백\n진도 {prog.get('steps_done')}/{prog.get('steps_total')}. "
                f"막힌 부분 방향만 안내합니다.", "mock-claude", 0.012)
    monkeypatch.setattr(fb_svc, "_claude_feedback", fake_cc)
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.drop_all)


async def _new() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _signup(client, email, name):
    r = await client.post("/auth/signup", json={"email": email, "password": "pass12345", "name": name})
    return r.json()["access_token"], r.json()["user"]["id"]


async def _make_admin(email):
    from sqlalchemy import select
    async with SessionLocal() as s:
        u = (await s.scalars(select(User).where(User.email == email))).first()
        u.role = "admin"; await s.commit()


@pytest.mark.asyncio
async def test_generate_feedback_service_manual():
    async with SessionLocal() as s:
        u = User(email="s@x", name="Stud", password_hash=hash_password("pass1234"))
        s.add(u); await s.flush()
        s.add(ProgressSnapshot(user_id=u.id, steps_done=1, steps_total=3, completion=33,
                               bottleneck_flags={"repeated_failed_commands": 4}))
        s.add(ActivityEvent(user_id=u.id, kind="command", payload={"cmd": "sqlmap", "rc": 1}))
        await s.commit()
        fb = await fb_svc.generate_feedback(s, user_id=u.id, trigger="manual", delivered_to="both")
    assert fb.model == "mock-claude"
    assert "피드백" in fb.content_md
    assert fb.basis["progress"]["steps_total"] == 3       # 근거 포함
    assert fb.cost_usd == int(round(0.012 * 1_000_000))


@pytest.mark.asyncio
async def test_bottleneck_trigger_cb():
    """lab_monitor 콜백 경로 — 병목 트리거."""
    async with SessionLocal() as s:
        from app.models import Scenario, Infra
        u = User(email="s2@x", name="S2", password_hash=hash_password("pass1234"))
        s.add(u); await s.flush()
        inf = Infra(owner_id=u.id, name="i", vm_ip="10.0.0.1", ssh_password_enc="x",
                    bastion_api_key="k", port_map={})
        s.add(inf)
        scn = Scenario(title="T", status="validated", mission_red={"missions": []},
                       mission_blue={"missions": []}, scoring={}, time_limit_sec=1800)
        s.add(scn); await s.flush()
        from app.services import battle_service as bs
        b = await bs.create_battle(s, scenario_id=scn.id, mode="solo", monitor="bastion",
                                   participants=[{"user_id": u.id, "role": "solo", "infra_id": inf.id}],
                                   created_by=u.id)
        await bs.start_battle(s, b.id, actor_user_id=u.id)
        await fb_svc.bottleneck_feedback_cb(s, b.id, u.id, {"stuck": True})
        from sqlalchemy import select
        fbs = (await s.scalars(select(StudentFeedback))).all()
    assert len(fbs) == 1
    assert fbs[0].trigger == "bottleneck"


@pytest.mark.asyncio
async def test_feedback_endpoints_and_permissions():
    async with await _new() as client:
        await _signup(client, "rooty@example.com", "rooty")
        await _make_admin("rooty@example.com")
        atok = (await client.post("/auth/login", json={
            "email": "rooty@example.com", "password": "pass12345"})).json()["access_token"]
        ah = {"authorization": f"Bearer {atok}"}
        s_tok, s_id = await _signup(client, "stud@example.com", "Stud")
        sh = {"authorization": f"Bearer {s_tok}"}

        # 학생은 생성 불가 (403)
        r = await client.post(f"/feedback/students/{s_id}", headers=sh,
                              json={"delivered_to": "both"})
        assert r.status_code == 403

        # admin on-demand 생성 (manual)
        r = await client.post(f"/feedback/students/{s_id}", headers=ah,
                              json={"scope": "lab", "delivered_to": "both"})
        assert r.status_code == 201, r.text
        fid = r.json()["id"]
        assert r.json()["trigger"] == "manual"

        # 학생은 본인 피드백 열람
        mine = (await client.get("/feedback/me", headers=sh)).json()
        assert any(f["id"] == fid for f in mine)

        # admin 검토 리스트
        rev = (await client.get(f"/feedback?user_id={s_id}", headers=ah)).json()
        assert len(rev) == 1

        # 재생성
        rg = await client.post(f"/feedback/{fid}/regenerate", headers=ah)
        assert rg.status_code == 201
        assert rg.json()["id"] != fid

        # instructor-only 전달 피드백은 학생에게 안 보임
        await client.post(f"/feedback/students/{s_id}", headers=ah,
                          json={"delivered_to": "instructor"})
        mine2 = (await client.get("/feedback/me", headers=sh)).json()
        assert all(f["delivered_to"] in ("student", "both") for f in mine2)
