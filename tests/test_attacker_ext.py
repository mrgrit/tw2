"""6v6 망 외부 attacker(attacker-ext) 반영 — 표면(2203) + 외부공격 공정 채점 근거/프롬프트."""
from __future__ import annotations
import os
import pytest

os.environ.setdefault("TUBEWAR_FERNET_KEY", "ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg=")

from app.services import six_smoke  # noqa: E402
from app.services import event_analyzer as ea  # noqa: E402
from app.services import assessor_client  # noqa: E402
from app.routers import battles  # noqa: E402


class FakeInfra:
    vm_ip = "10.0.0.5"
    bastion_api_key = "k"
    port_map: dict = {}


def test_smoke_includes_attacker_ext_port():
    assert six_smoke.DEFAULT_PORTS["attacker_ext_ssh"] == 2203
    keys = {k for _, k, _, _ in six_smoke.PORT_SPEC}
    assert "attacker_ext_ssh" in keys
    # 옵셔널(required=False) 이어야 — SKIP_ATTACKER_EXT 가능
    spec = {k: req for _, k, req, _ in six_smoke.PORT_SPEC}
    assert spec["attacker_ext_ssh"] is False
    # 기존 attacker(insider) 는 유지
    assert six_smoke.DEFAULT_PORTS["attacker_ssh"] == 2202


def test_resolve_ports_override_attacker_ext():
    p = six_smoke.resolve_ports({"attacker_ext_ssh": 12203})
    assert p["attacker_ext_ssh"] == 12203


def test_grade_prompt_has_two_attacker_model():
    sysprompt = ea._CLAUDE_GRADE_SYSTEM
    assert "attacker-ext" in sysprompt
    # 외부 attacker command_ran 신뢰 금지 + 타깃 흔적 판정 지침
    assert "command_ran" in sysprompt and ("UNRELIABLE" in sysprompt or "unreliable" in sysprompt.lower())
    assert "target" in sysprompt.lower()


@pytest.mark.asyncio
async def test_initial_evidence_external_caveat(monkeypatch):
    async def fake_activity(infra, **kw):
        return {"ok": True, "commands": [{"cmd": "curl ..."}], "fim": [], "alerts": [], "services": {}}

    async def fake_assess(infra, checks, **kw):
        return {"ok": True, "results": [{"id": "c1", "passed": True, "evidence": "modsec hit"}]}

    monkeypatch.setattr(assessor_client, "activity", fake_activity)
    monkeypatch.setattr(assessor_client, "assess", fake_assess)
    mission_raw = {"order": 1, "target_vm": "web", "assess_target": "opponent",
                   "verify": {"type": "log_contains", "log": "modsec", "pattern": "union"}}

    ext = await battles._initial_evidence(FakeInfra(), FakeInfra(), mission_raw, "red", external=True)
    assert "attacker-ext" in ext and "command_ran" in ext   # caveat 포함
    assert "타깃" in ext                                      # 타깃 흔적 강조

    nonext = await battles._initial_evidence(FakeInfra(), FakeInfra(), mission_raw, "blue", external=False)
    assert "attacker-ext" not in nonext                       # 내부 미션엔 caveat 없음
