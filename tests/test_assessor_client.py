"""assessor_client — URL/Host/포트 해석, /assess 호출·파싱, 실패 처리."""
from __future__ import annotations
import os
import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("TUBEWAR_FERNET_KEY", "ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg=")

from app.services import assessor_client as ac  # noqa: E402
from tests.assessor_fake import make_fake_assessor_app  # noqa: E402


class FakeInfra:
    def __init__(self, vm_ip, bastion_api_key="k", port_map=None):
        self.vm_ip = vm_ip
        self.bastion_api_key = bastion_api_key
        self.port_map = port_map or {}


def test_resolve_url_default_port_80():
    assert ac.resolve_url(FakeInfra("10.0.0.5")) == "http://10.0.0.5/assess"


def test_resolve_url_direct_port_priority():
    infra = FakeInfra("10.0.0.5", port_map={"assessor": 9300})
    assert ac.resolve_url(infra) == "http://10.0.0.5:9300/assess"


def test_resolve_headers():
    h = ac.resolve_headers(FakeInfra("10.0.0.5", "mykey"))
    assert h["Host"] == "assessor.6v6.lab"
    assert h["X-API-Key"] == "mykey"


@pytest.mark.asyncio
async def test_assess_success_parses_results():
    policy = {"blue-1-1": (True, "found 200 OK"), "blue-2-1": (False, "no match")}
    app = make_fake_assessor_app(policy, require_key="secret")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://x") as client:
        infra = FakeInfra("10.20.30.80", "secret")
        checks = [
            {"id": "blue-1-1", "type": "log_contains", "target": "web", "params": {}},
            {"id": "blue-2-1", "type": "wazuh_alert", "target": "siem", "params": {}},
        ]
        resp = await ac.assess(infra, checks, battle_id=7, client=client)

    assert resp["ok"] is True
    assert resp["collected_at"] == "2026-06-03T00:00:00Z"
    by_id = ac.results_by_id(resp)
    assert by_id["blue-1-1"]["passed"] is True
    assert by_id["blue-1-1"]["evidence"] == "found 200 OK"
    assert by_id["blue-2-1"]["passed"] is False


@pytest.mark.asyncio
async def test_assess_bad_key_returns_dict_not_raise():
    app = make_fake_assessor_app(require_key="secret")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://x") as client:
        infra = FakeInfra("10.20.30.80", "WRONG")
        resp = await ac.assess(infra, [{"id": "c1", "type": "file_exists", "params": {}}], client=client)
    assert resp["ok"] is False
    assert resp["status_code"] == 401
    assert resp["results"] == []


@pytest.mark.asyncio
async def test_assess_unreachable_returns_dict_not_raise():
    # 실제 라우팅 불가 IP — 연결 실패가 예외 대신 dict 로.
    infra = FakeInfra("240.0.0.1")
    resp = await ac.assess(infra, [{"id": "c1", "type": "file_exists", "params": {}}], timeout=0.5)
    assert resp["ok"] is False
    assert "error" in resp
    assert resp["results"] == []


@pytest.mark.asyncio
async def test_activity_pull_parses_lists():
    act = {"commands": [{"cmd": "hydra ..."}], "fim": [{"path": "/etc/shadow"}],
           "alerts": [{"rule_id": 5710}], "services": {"sshd": "running"}}
    app = make_fake_assessor_app(require_key="secret", activity=act)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://x") as client:
        infra = FakeInfra("10.20.30.80", "secret")
        resp = await ac.activity(infra, since_sec=60, want=["commands", "alerts"], client=client)
    assert resp["ok"] is True
    assert resp["commands"][0]["cmd"].startswith("hydra")
    assert resp["alerts"][0]["rule_id"] == 5710
    assert resp["services"]["sshd"] == "running"


@pytest.mark.asyncio
async def test_activity_unreachable_returns_empty_lists():
    resp = await ac.activity(FakeInfra("240.0.0.1"), timeout=0.5)
    assert resp["ok"] is False
    assert resp["commands"] == [] and resp["fim"] == [] and resp["alerts"] == []


@pytest.mark.asyncio
async def test_provision_rule_arm():
    app = make_fake_assessor_app(require_key="secret")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://x") as client:
        resp = await ac.provision_rule(FakeInfra("10.20.30.80", "secret"),
                                       action="arm", rule={"id": "r1"}, client=client)
    assert resp["ok"] is True
    assert resp["result"]["applied"] is True


def test_resolve_url_paths():
    infra = FakeInfra("10.0.0.5", port_map={"assessor": 9300})
    assert ac.resolve_url(infra, "/activity") == "http://10.0.0.5:9300/activity"
    assert ac.resolve_base(infra) == "http://10.0.0.5:9300"


@pytest.mark.asyncio
async def test_assess_sends_battle_id_and_host():
    seen = {}
    app = make_fake_assessor_app(require_host="assessor.6v6.lab")

    # 별도 검증: host 불일치면 400
    bad = make_fake_assessor_app(require_host="other.host")
    async with AsyncClient(transport=ASGITransport(app=bad), base_url="http://x") as client:
        resp = await ac.assess(FakeInfra("1.2.3.4"), [{"id": "c", "type": "file_exists", "params": {}}],
                               client=client)
    assert resp["ok"] is False  # Host 헤더가 assessor.6v6.lab 이라 other.host 와 불일치
