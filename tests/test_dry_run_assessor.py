"""dry_run.assess_reachability — 실제 /assess 로 check-spec reachability·정합성 (pass_rate≥0.7→validated)."""
from __future__ import annotations
import os
import pytest

os.environ.setdefault("TUBEWAR_FERNET_KEY", "ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg=")

from app.services import dry_run  # noqa: E402
from app.services import assessor_client  # noqa: E402
from tests.assessor_fake import build_fake_assess  # noqa: E402


class FakeInfra:
    vm_ip = "10.20.30.80"
    bastion_api_key = "k"
    port_map: dict = {}


SCEN = {
    "mission_red": {"missions": [
        {"order": 1, "target_vm": "attacker", "verify": {"type": "output_contains", "expect": "hydra"}},
    ]},
    "mission_blue": {"missions": [
        {"order": 1, "target_vm": "web", "verify": {"type": "output_contains", "expect": "Failed"}},
        {"order": 2, "target_vm": "siem", "verify": {"type": "wazuh_alert", "rule_id": "5710"}},
    ]},
}


@pytest.mark.asyncio
async def test_assess_reachability_all_pass_validated(monkeypatch):
    monkeypatch.setattr(assessor_client, "assess", build_fake_assess())  # 전부 pass
    out = await dry_run.assess_reachability(SCEN, FakeInfra())
    assert out["ok"] is True
    assert out["total"] == 3      # red 1 + blue 2
    assert out["passed"] == 3
    assert out["pass_rate"] == 1.0
    assert out["validated"] is True


@pytest.mark.asyncio
async def test_assess_reachability_below_threshold_not_validated(monkeypatch):
    # 3개 중 1개만 pass → pass_rate 0.33 < 0.7
    seen = {"n": 0}

    def policy(check):
        seen["n"] += 1
        return (seen["n"] == 1, "ev")

    monkeypatch.setattr(assessor_client, "assess", build_fake_assess(policy=policy))
    out = await dry_run.assess_reachability(SCEN, FakeInfra())
    assert out["passed"] == 1
    assert out["pass_rate"] < 0.7
    assert out["validated"] is False
