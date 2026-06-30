"""미션 IP 런타임 치환(infra_render) 단위 테스트."""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "api"))

from app.services import infra_render as ir


class _Inf:
    def __init__(self, vm_ip=None, web_entry_ip=None, kind="target", name=""):
        self.vm_ip = vm_ip
        self.web_entry_ip = web_entry_ip
        self.kind = kind
        self.name = name


def test_build_vars_falls_back_to_reference_defaults():
    from app.config import get_settings
    s = get_settings()
    v = ir.build_vars(None, None)
    # 폴백 = config(.env TUBEWAR_REF_*) 값. IP 는 가변이라 리터럴 대신 설정값으로 검증.
    assert v["TARGET_IP"] == s.ref_target_ip
    assert v["WEB_ENTRY"] == s.ref_web_entry
    assert v["ATTACKER_IP"] == s.ref_attacker_ip


def test_build_vars_uses_registered_infra():
    target = _Inf(vm_ip="10.0.0.51", web_entry_ip="10.0.0.61", kind="target")
    attacker = _Inf(vm_ip="10.0.0.202", kind="attacker")
    v = ir.build_vars(target, attacker)
    assert v == {"TARGET_IP": "10.0.0.51", "WEB_ENTRY": "10.0.0.61", "ATTACKER_IP": "10.0.0.202"}


def test_web_entry_falls_back_to_vm_ip_when_unset():
    v = ir.build_vars(_Inf(vm_ip="10.0.0.51", web_entry_ip=None), _Inf(vm_ip="10.0.0.9", kind="attacker"))
    assert v["WEB_ENTRY"] == "10.0.0.51"  # web_entry 미설정 → vm_ip 폴백


def test_render_replaces_tokens_recursively_and_keeps_unknown():
    v = {"TARGET_IP": "1.1.1.1", "WEB_ENTRY": "2.2.2.2", "ATTACKER_IP": "3.3.3.3"}
    obj = {
        "instruction": "curl http://{{WEB_ENTRY}}/x from {{ATTACKER_IP}} ssh {{TARGET_IP}}:9201",
        "nested": ["{{TARGET_IP}}", {"deep": "{{UNKNOWN}} stays"}],
        "n": 5,
    }
    out = ir.render(obj, v)
    assert out["instruction"] == "curl http://2.2.2.2/x from 3.3.3.3 ssh 1.1.1.1:9201"
    assert out["nested"][0] == "1.1.1.1"
    assert out["nested"][1]["deep"] == "{{UNKNOWN}} stays"  # 모르는 토큰은 보존
    assert out["n"] == 5


def test_split_infras_by_kind_and_heuristic():
    t = _Inf(vm_ip="t", kind="target", name="el34")
    a = _Inf(vm_ip="a", kind="attacker", name="atk")
    tt, aa = ir.split_infras([a, t])
    assert tt is t and aa is a
    # kind 없이 name 휴리스틱
    a2 = _Inf(vm_ip="a2", kind="", name="my-attacker")
    t2 = _Inf(vm_ip="t2", kind="", name="el34-target")
    tt2, aa2 = ir.split_infras([a2, t2])
    assert aa2 is a2 and tt2 is t2
    # 하나뿐이면 양쪽 동일
    only = _Inf(vm_ip="x", kind="target")
    tt3, aa3 = ir.split_infras([only])
    assert tt3 is only and aa3 is only


def test_vars_for_battle_duel_maps_red_attacker_blue_target():
    red = _Inf(vm_ip="10.0.0.202", kind="attacker")
    blue = _Inf(vm_ip="10.0.0.51", web_entry_ip="10.0.0.61", kind="target")
    v = ir.vars_for_battle({"red": red, "blue": blue})
    assert v["ATTACKER_IP"] == "10.0.0.202"
    assert v["TARGET_IP"] == "10.0.0.51"
    assert v["WEB_ENTRY"] == "10.0.0.61"
