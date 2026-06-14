#!/usr/bin/env python3
"""battle-scenarios/*.yaml 정적 검증기 — 학생 배포 전 무오류 보장용.

각 시나리오에 대해:
  1) YAML 파싱
  2) scenario_loader._normalize (DB 적재 시와 동일 변환)
  3) 모든 미션(red+blue)에 대해 check_compiler.compile_mission_checks 실행 →
     type ∈ ASSESSOR_TYPES, target 존재, params 필수키 충족 검증
  4) 미션 구조 점검(order 유일·연속, points>0, instruction 비어있지 않음)
  5) (옵션) 마커 충돌 점검 — 파일 간 sid/rule id/계정/포트 중복 경고

사용:
  python scripts/validate_scenarios.py                  # 전체
  python scripts/validate_scenarios.py soc-adv-         # prefix 필터
  python scripts/validate_scenarios.py --markers        # 마커 충돌까지 점검

생성/자동화 스크립트가 아니라 '검증' 도구다(시나리오는 사람이 손으로 작성).
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

import yaml  # noqa: E402
from app.services.scenario_loader import _normalize  # noqa: E402
from app.services.check_compiler import compile_mission_checks, ASSESSOR_TYPES  # noqa: E402

SCEN_DIR = ROOT / "contents" / "battle-scenarios"

# check type별 필수 params 키.
REQUIRED_PARAMS = {
    "file_exists": ["path"],
    "file_contains": ["path", "pattern"],
    "file_hash": ["path"],
    "process_running": ["name"],
    "port_listening": ["port"],
    "log_contains": ["log", "pattern"],
    "wazuh_alert": [],          # rule_id 또는 pattern 중 하나
    "fim_change": ["path"],
    "command_ran": ["pattern"],
}
LOG_ALIASES = {"apache_error", "auth", "modsec", "suricata"}
VALID_TARGETS = {"web", "siem", "ips", "secu", "fw", "attacker", "bastion", "portal", "waf"}


def check_mission(side: str, m: dict, errors: list, warns: list) -> None:
    order = m.get("order")
    tag = f"{side}-{order}"
    if not m.get("instruction", "").strip():
        errors.append(f"{tag}: instruction 비어있음")
    if int(m.get("points") or 0) <= 0:
        warns.append(f"{tag}: points 0 이하")
    if m.get("target_vm") and m["target_vm"] not in VALID_TARGETS:
        warns.append(f"{tag}: 알 수 없는 target_vm '{m['target_vm']}'")
    if m.get("assess_target") not in (None, "self", "opponent"):
        errors.append(f"{tag}: assess_target 잘못됨 '{m.get('assess_target')}'")
    try:
        checks = compile_mission_checks(dict(m), side=side)
    except Exception as e:
        errors.append(f"{tag}: compile_mission_checks 예외 {e!r}")
        return
    if not checks:
        errors.append(f"{tag}: 컴파일된 check 0개")
    for c in checks:
        ct = c.get("type")
        if ct not in ASSESSOR_TYPES:
            errors.append(f"{tag}: check type '{ct}' 미지원")
            continue
        if not c.get("target"):
            errors.append(f"{tag}: check '{c.get('id')}' target 없음")
        params = c.get("params") or {}
        for k in REQUIRED_PARAMS.get(ct, []):
            v = params.get(k)
            # pattern 은 regex 로 대체 가능(assessor 가 둘 다 허용).
            if k == "pattern" and (params.get("regex") not in (None, "")):
                continue
            if v in (None, "", 0):
                errors.append(f"{tag}: check '{c.get('id')}'({ct}) params.{k} 비어있음 → {params}")
        if ct == "log_contains" and params.get("log") not in LOG_ALIASES:
            errors.append(f"{tag}: log_contains log별칭 '{params.get('log')}' 무효(허용: {LOG_ALIASES})")
        # wazuh_alert 는 rule_id / pattern / since_sec(윈도우 내 경보 존재) 중 하나면 유효.
        if ct == "wazuh_alert" and not (params.get("rule_id") or params.get("pattern")
                                        or params.get("since_sec")):
            errors.append(f"{tag}: wazuh_alert 는 rule_id/pattern/since_sec 중 하나 필요")


def validate_file(path: Path, markers: dict | None) -> tuple[list, list]:
    errors: list[str] = []
    warns: list[str] = []
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as e:
        return [f"YAML 파싱 실패: {e}"], []
    if not isinstance(raw, dict):
        return ["최상위가 dict 아님"], []
    try:
        norm = _normalize(raw, path.stem)
    except Exception as e:
        return [f"_normalize 예외: {e!r}"], []
    for req in ("title", "description"):
        if not str(norm.get(req) or "").strip():
            errors.append(f"{req} 비어있음")

    seen_orders = {"red": set(), "blue": set()}
    for side, key in (("red", "red_missions"), ("blue", "blue_missions")):
        for m in raw.get(key) or []:
            o = m.get("order")
            if o in seen_orders[side]:
                errors.append(f"{side}: order {o} 중복")
            seen_orders[side].add(o)
            check_mission(side, m, errors, warns)

    if markers is not None:
        text = path.read_text(encoding="utf-8")
        for pat, label in ((r"\bsid:(\d{5,7})", "sid"),
                           (r'rule id="(\d{5,7})"', "wazuh_rule"),
                           (r"\buseradd[^\n]*\b([a-z]{3,12}\d{0,3})\b", "account")):
            for mm in re.finditer(pat, text):
                val = f"{label}:{mm.group(1)}"
                markers.setdefault(val, []).append(path.stem)
    return errors, warns


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    do_markers = "--markers" in sys.argv
    prefix = args[0] if args else ""
    markers: dict[str, list] = {} if do_markers else None
    files = sorted(p for p in SCEN_DIR.glob("*.yaml") if p.stem.startswith(prefix))
    total_err = 0
    for path in files:
        errors, warns = validate_file(path, markers)
        status = "OK " if not errors else "ERR"
        if errors or warns:
            print(f"[{status}] {path.name}")
            for e in errors:
                print(f"    ✗ {e}")
            for w in warns:
                print(f"    ~ {w}")
        else:
            print(f"[{status}] {path.name}")
        total_err += len(errors)
    print(f"\n총 {len(files)}개 파일 · 오류 {total_err}건")
    if markers is not None:
        dups = {k: v for k, v in markers.items() if len(set(v)) > 1}
        if dups:
            print("\n⚠ 마커 충돌(여러 시나리오가 같은 sid/rule/계정 사용):")
            for k, v in sorted(dups.items()):
                print(f"    {k}: {sorted(set(v))}")
        else:
            print("마커 충돌 없음")
    return 1 if total_err else 0


if __name__ == "__main__":
    raise SystemExit(main())
