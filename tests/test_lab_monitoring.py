"""lab_monitor — /activity→타임라인 적재, 진도 계산, 병목 결정론 신호→(mock CC) 피드백,
cohort 태깅, 신원-only, 결정론 신호 LLM 0."""
from __future__ import annotations
import os
import pytest
import pytest_asyncio

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("TUBEWAR_JWT_SECRET", "test-secret-32-chars-please-not-shorter")
os.environ.setdefault("TUBEWAR_FERNET_KEY", "ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg=")

from sqlalchemy import select  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.models import ActivityEvent, Cohort, Infra, Scenario, User  # noqa: E402
from app.security import hash_password  # noqa: E402
from app.services import battle_service as bs, lab_monitor  # noqa: E402
from app.services import assessor_client  # noqa: E402
from tests.assessor_fake import build_fake_activity  # noqa: E402


@pytest_asyncio.fixture(autouse=True)
async def _reset():
    lab_monitor._last_progress_ts.clear()
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.drop_all)
    lab_monitor._last_progress_ts.clear()


async def _make_battle(cohort=False, blue_missions=None):
    async with SessionLocal() as s:
        u = User(email="a@x", name="A", password_hash=hash_password("pass1234"))
        s.add(u); await s.flush()
        inf = Infra(owner_id=u.id, name="a", vm_ip="10.0.0.1",
                    ssh_password_enc="x", bastion_api_key="k", port_map={})
        s.add(inf)
        cid = None
        if cohort:
            c = Cohort(kind="section", name="A")
            s.add(c); await s.flush(); cid = c.id
        scn = Scenario(title="T", status="validated",
                       mission_red={"missions": []},
                       mission_blue={"missions": blue_missions or [
                           {"order": 1, "instruction": "m1", "points": 10, "target_vm": "web",
                            "verify": {"type": "output_contains", "expect": "x"}},
                           {"order": 2, "instruction": "m2", "points": 10, "target_vm": "web",
                            "verify": {"type": "output_contains", "expect": "y"}},
                       ]},
                       scoring={}, time_limit_sec=1800)
        s.add(scn); await s.flush()
        b = await bs.create_battle(s, scenario_id=scn.id, mode="solo", monitor="bastion",
                                   participants=[{"user_id": u.id, "role": "solo", "infra_id": inf.id}],
                                   created_by=u.id, cohort_id=cid)
        await bs.start_battle(s, b.id, actor_user_id=u.id)
        return b.id, u.id, cid


@pytest.mark.asyncio
async def test_activity_ingest_timeline_and_cohort_tag(monkeypatch):
    bid, uid, cid = await _make_battle(cohort=True)
    payload = {"commands": [{"cmd": "nmap -sV target", "rc": 0}],
               "fim": [{"path": "/etc/nginx/nginx.conf"}],
               "alerts": [{"rule_id": 5710, "desc": "ssh brute"}]}
    monkeypatch.setattr(assessor_client, "activity", build_fake_activity(payload))
    async with SessionLocal() as s:
        res = await lab_monitor.pull_activity_once(s, bid)
    assert res["ingested"] == 3
    async with SessionLocal() as s:
        evs = (await s.scalars(select(ActivityEvent).where(ActivityEvent.battle_id == bid))).all()
    kinds = sorted(e.kind for e in evs)
    assert kinds == ["alert", "command", "fim"]
    assert all(e.cohort_id == cid and e.user_id == uid for e in evs)  # 서버측 cohort 태깅


@pytest.mark.asyncio
async def test_activity_dedupe_no_double_ingest(monkeypatch):
    bid, uid, cid = await _make_battle()
    payload = {"commands": [{"cmd": "ls", "rc": 0}], "alerts": [{"rule_id": 1}]}
    monkeypatch.setattr(assessor_client, "activity", build_fake_activity(payload))
    async with SessionLocal() as s:
        await lab_monitor.pull_activity_once(s, bid)
    async with SessionLocal() as s:
        res2 = await lab_monitor.pull_activity_once(s, bid)   # 동일 활동 재pull
    assert res2["ingested"] == 0
    async with SessionLocal() as s:
        n = len((await s.scalars(select(ActivityEvent).where(ActivityEvent.battle_id == bid))).all())
    assert n == 2


@pytest.mark.asyncio
async def test_progress_computation(monkeypatch):
    bid, uid, cid = await _make_battle()
    # mission 1 을 auto_monitor 가 solved 로 표기 (BattleEvent)
    async with SessionLocal() as s:
        await bs.add_event(s, battle_id=bid, actor_user_id=uid, event_type="detect",
                           target="web", description="auto", points=10,
                           detail={"source": "auto_monitor", "blue_mission_order": 1})
        prog = await lab_monitor.snapshot_progress(s, bid)
    me = prog[0]
    assert me["steps_total"] == 2
    assert me["steps_done"] == 1
    assert me["completion"] == 50.0


@pytest.mark.asyncio
async def test_bottleneck_triggers_feedback_only_for_stuck(monkeypatch):
    bid, uid, cid = await _make_battle()
    # 실패 명령 다수 → repeated_failed_commands 병목
    payload = {"commands": [{"cmd": f"sqlmap try{i}", "rc": 1, "stderr": "error"} for i in range(4)]}
    monkeypatch.setattr(assessor_client, "activity", build_fake_activity(payload))

    called = []

    async def fake_feedback(session, battle_id, user_id, progress):
        called.append(user_id)  # mock CC — stuck 학생만 호출돼야

    res = await lab_monitor.run_lab_tick(bid, feedback_cb=fake_feedback)
    assert res["ingested"] == 4
    assert res["stuck"] == 1
    assert called == [uid]   # 결정론 게이팅: 막힌 학생만 CC


@pytest.mark.asyncio
async def test_no_bottleneck_no_feedback(monkeypatch):
    bid, uid, cid = await _make_battle()
    payload = {"commands": [{"cmd": "nmap", "rc": 0}]}  # 정상 — 병목 없음
    monkeypatch.setattr(assessor_client, "activity", build_fake_activity(payload))
    called = []

    async def fake_feedback(session, battle_id, user_id, progress):
        called.append(user_id)

    res = await lab_monitor.run_lab_tick(bid, feedback_cb=fake_feedback)
    assert res["stuck"] == 0
    assert called == []      # CC 호출 0 (LLM 0)


@pytest.mark.asyncio
async def test_lab_tick_exports_activity_to_siem(monkeypatch):
    """pull 한 활동이 중앙 SIEM(export_events)으로 코호트 stamp 되어 적재되도록 배선됐는지."""
    from app.services import siem_export
    bid, uid, cid = await _make_battle(cohort=True)
    payload = {"commands": [{"cmd": "nmap target", "rc": 0}],
               "alerts": [{"rule_id": 5710}]}
    monkeypatch.setattr(assessor_client, "activity", build_fake_activity(payload))

    calls = {}
    monkeypatch.setattr(siem_export, "is_enabled", lambda: True)
    monkeypatch.setattr(siem_export, "default_client", lambda: object())

    async def fake_export(client, events, chain):
        calls["events"] = events
        calls["chain_ids"] = [c.id for c in chain]
        return {"indexed": len(events), "index": "tubewar-activity-x"}

    async def fake_ensure(client, chain):
        calls["ensured"] = True
        return {"created": []}

    monkeypatch.setattr(siem_export, "export_events", fake_export)
    monkeypatch.setattr(siem_export, "ensure_cohort_objects", fake_ensure)

    res = await lab_monitor.run_lab_tick(bid)
    assert res["siem_exported"] == 2            # command + alert
    assert len(calls["events"]) == 2
    assert calls["chain_ids"] == [cid]          # 코호트 stamp (서브트리 체인)
    assert calls.get("ensured") is True


@pytest.mark.asyncio
async def test_lab_tick_siem_noop_when_disabled(monkeypatch):
    from app.services import siem_export
    bid, uid, cid = await _make_battle(cohort=True)
    monkeypatch.setattr(assessor_client, "activity",
                        build_fake_activity({"commands": [{"cmd": "ls"}]}))
    monkeypatch.setattr(siem_export, "is_enabled", lambda: False)   # 미설정 → no-op
    res = await lab_monitor.run_lab_tick(bid)
    assert res["siem_exported"] == 0


@pytest.mark.asyncio
async def test_identity_only_lab_monitor(monkeypatch):
    bid, uid, cid = await _make_battle(cohort=False)
    assert cid is None
    payload = {"commands": [{"cmd": "ls", "rc": 0}]}
    monkeypatch.setattr(assessor_client, "activity", build_fake_activity(payload))
    res = await lab_monitor.run_lab_tick(bid)
    assert res["ingested"] == 1
    async with SessionLocal() as s:
        evs = (await s.scalars(select(ActivityEvent).where(ActivityEvent.battle_id == bid))).all()
    assert all(e.cohort_id is None for e in evs)   # 신원-only 정상
