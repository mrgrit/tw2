"""check_compiler — 각 Assessor check type 매핑 + semantic→checks 캐시 + target_vm 해석."""
from __future__ import annotations
import os

os.environ.setdefault("TUBEWAR_FERNET_KEY", "ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg=")

from app.services import check_compiler as cc  # noqa: E402


def _compile_one(mission, side="blue"):
    checks = cc.compile_mission_checks(mission, side=side)
    assert len(checks) == 1
    return checks[0]


def test_direct_file_exists():
    c = _compile_one({"order": 1, "target_vm": "web",
                      "verify": {"type": "file_exists", "path": "/etc/passwd"}})
    assert c["type"] == "file_exists"
    assert c["params"]["path"] == "/etc/passwd"
    assert c["target"] == "web"


def test_direct_file_contains():
    c = _compile_one({"order": 2, "target_vm": "secu",
                      "verify": {"type": "file_contains", "path": "/var/ossec/etc/ossec.conf",
                                 "pattern": "active-response"}})
    assert c["type"] == "file_contains"
    assert c["params"] == {"path": "/var/ossec/etc/ossec.conf", "pattern": "active-response"}


def test_direct_process_running():
    c = _compile_one({"order": 3, "target_vm": "web",
                      "verify": {"type": "process_running", "process": "apache2"}})
    assert c["type"] == "process_running"
    assert c["params"]["name"] == "apache2"


def test_direct_port_listening():
    c = _compile_one({"order": 4, "target_vm": "web",
                      "verify": {"type": "port_listening", "port": 443}})
    assert c["type"] == "port_listening"
    assert c["params"]["port"] == 443
    assert c["params"]["proto"] == "tcp"


def test_direct_command_ran():
    c = _compile_one({"order": 5, "target_vm": "attacker",
                      "verify": {"type": "command_ran", "pattern": "sqlmap"}})
    assert c["type"] == "command_ran"
    assert c["params"]["pattern"] == "sqlmap"


def test_infer_log_contains_from_output_contains():
    # blue: auth.log 의 Failed password 분석 → log_contains
    m = {"order": 2, "target_vm": "web",
         "verify": {"type": "output_contains", "expect": "Failed",
                    "semantic": {"intent": "auth.log 의 Failed password 분석",
                                 "success_criteria": ["/var/log/auth.log grep 'Failed password'"]}}}
    c = _compile_one(m)
    assert c["type"] == "log_contains"
    assert c["params"]["path"] == "/var/log/auth.log"
    assert c["params"]["pattern"] == "Failed"


def test_infer_wazuh_alert_with_rule_id():
    m = {"order": 5, "target_vm": "siem",
         "verify": {"type": "output_contains", "expect": "alert",
                    "semantic": {"intent": "Wazuh sshd brute force rule 5710/5712 매칭",
                                 "success_criteria": ["alerts.json grep 5710/5712/brute"]}}}
    c = _compile_one(m)
    assert c["type"] == "wazuh_alert"
    assert c["params"].get("rule_id") == "5710"


def test_infer_command_ran_red_attacker():
    # red: hydra brute force → command_ran pattern hydra
    m = {"order": 1, "target_vm": "attacker",
         "verify": {"type": "output_contains", "expect": "hydra",
                    "semantic": {"intent": "MITRE T1110.001 brute force"}}}
    c = _compile_one(m, side="red")
    assert c["type"] == "command_ran"
    assert c["params"]["pattern"] == "hydra"
    assert c["id"].startswith("red-1")


def test_empty_expect_falls_back_to_command_token():
    # nftables 설정 — expect 빈 문자열, hint 의 nft 토큰 사용
    m = {"order": 3, "target_vm": "secu",
         "instruction": "nftables로 공격자 IP의 SSH 접근을 차단하라",
         "hint": "nft add rule inet filter input ip saddr 10.20.30.201 tcp dport 22 drop",
         "verify": {"type": "output_contains", "expect": ""}}
    c = _compile_one(m)
    assert c["type"] == "command_ran"
    assert c["params"]["pattern"] == "nft"


def test_cache_checks_idempotent_and_reused():
    m = {"order": 1, "target_vm": "attacker",
         "verify": {"type": "output_contains", "expect": "hydra"}}
    checks1 = cc.cache_checks_into_mission(m, side="red")
    # 캐시가 mission 에 박혀야
    assert m["verify"]["checks"] == checks1
    # 두 번째 호출은 캐시 그대로 반환 (재컴파일 없음)
    checks2 = cc.cache_checks_into_mission(m, side="red")
    assert checks2 is checks1 or checks2 == checks1
    # compile_mission_checks 도 캐시 우선
    assert cc.compile_mission_checks(m, side="red") == checks1


def test_target_vm_resolution_propagates():
    m = {"order": 7, "target_vm": "neobank",
         "verify": {"type": "output_contains", "expect": "200 OK"}}
    c = _compile_one(m)
    assert c["target"] == "neobank"


def test_compile_side_caches_all():
    missions = [
        {"order": 1, "target_vm": "web", "verify": {"type": "output_contains", "expect": "POST"}},
        {"order": 2, "target_vm": "siem", "verify": {"type": "output_contains", "expect": "alert",
                                                       "semantic": {"intent": "wazuh rule 5710"}}},
    ]
    all_checks = cc.compile_side(missions, side="blue")
    assert len(all_checks) == 2
    assert all("checks" in m["verify"] for m in missions)
