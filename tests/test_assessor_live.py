"""라이브 통합 테스트 — 실 6v6 Assessor 와 왕복. (기본 skip)

실행: ASSESSOR_LIVE=1 VM_IP=192.168.0.80 [ASSESSOR_KEY=ccc-api-key-2026] pytest -k live -v

check_compiler 가 만든 check-spec 이 **실 Assessor 가 이해하는 파라미터 형태**인지(특히
log_contains 의 log 별칭) 계약을 end-to-end 로 검증한다 — mock 만으로는 못 잡는 결함 방지.
"""
from __future__ import annotations
import os
import pytest

os.environ.setdefault("TUBEWAR_FERNET_KEY", "ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg=")

from app.services import assessor_client as ac  # noqa: E402
from app.services import check_compiler as cc  # noqa: E402

LIVE = os.getenv("ASSESSOR_LIVE") == "1"
VM_IP = os.getenv("VM_IP", "192.168.0.80")
KEY = os.getenv("ASSESSOR_KEY", "ccc-api-key-2026")

pytestmark = pytest.mark.skipif(not LIVE, reason="ASSESSOR_LIVE=1 + VM_IP 필요")


class LiveInfra:
    vm_ip = VM_IP
    bastion_api_key = KEY
    port_map: dict = {}   # 80 + Host 헤더


@pytest.mark.asyncio
async def test_live_assess_file_exists_pass_fail():
    infra = LiveInfra()
    resp = await ac.assess(infra, [
        {"id": "p", "type": "file_exists", "target": "web", "params": {"path": "/etc/passwd"}},
        {"id": "f", "type": "file_exists", "target": "web", "params": {"path": "/no/such/xyz"}},
    ])
    assert resp["ok"] is True, resp
    by = ac.results_by_id(resp)
    assert by["p"]["passed"] is True and by["p"]["evidence"]
    assert by["f"]["passed"] is False


@pytest.mark.asyncio
async def test_live_compiled_log_contains_is_accepted():
    """check_compiler 의 log_contains 가 실 Assessor 에서 error 없이 평가되는지(계약 일치)."""
    infra = LiveInfra()
    mission = {"order": 1, "target_vm": "web",
               "verify": {"type": "log_contains", "log": "modsec", "pattern": "sqlmap"}}
    checks = cc.compile_mission_checks(mission, side="blue")
    assert checks[0]["params"].get("log"), "compiler 가 log 별칭을 내야 함"
    resp = await ac.assess(infra, checks)
    assert resp["ok"] is True, resp
    r = resp["results"][0]
    # 핵심: error(미지원 별칭 등)로 거부되지 않고 boolean 으로 평가돼야 한다.
    assert r["passed"] in (True, False), r
    assert not (r.get("raw") or {}).get("error")


@pytest.mark.asyncio
async def test_live_activity_returns_lists():
    infra = LiveInfra()
    resp = await ac.activity(infra, since_sec=3600)
    assert resp["ok"] is True, resp
    assert isinstance(resp["commands"], list)
    assert isinstance(resp["alerts"], list)
    assert isinstance(resp["services"], dict)


@pytest.mark.asyncio
async def test_live_auth_required():
    bad = LiveInfra(); bad.bastion_api_key = "WRONG-KEY"
    resp = await ac.assess(bad, [{"id": "a", "type": "file_exists", "target": "web", "params": {"path": "/etc/passwd"}}])
    assert resp["ok"] is False   # 401 → dict(no raise)
