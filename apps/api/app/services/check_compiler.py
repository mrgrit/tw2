"""미션 → 6v6 Assessor check-spec[] 컴파일러.

미션의 `verify`(type/expect/semantic/target_vm) 를 Assessor `/assess` 가 이해하는
check-spec 리스트로 변환한다. check-spec 형태:

    {"id": "<side>-<order>-<n>", "type": "<assessor_type>", "target": "<vm>", "params": {...}}

Assessor type: file_exists, file_contains, file_hash, process_running, port_listening,
log_contains, wazuh_alert, fim_change, command_ran.

설계 원칙:
- **런타임 채점은 AI 0**: 컴파일 결과를 `mission["verify"]["checks"]` 에 캐시하고,
  auto_monitor/grader 는 그 캐시를 재사용한다.
- 결정론 매핑: `verify.type` 이 이미 Assessor type 이면 그대로 변환.
- `output_contains`(레거시) 는 target_vm + expect + semantic 으로 type 을 추론.
- `verify.semantic` 만 있고 구체 check 가 모호하면, **시나리오 생성/dry-run 시점에만**
  claude 1회로 정제할 수 있다(`llm_refine_checks`). 런타임에서는 절대 호출하지 않는다.
"""
from __future__ import annotations
import json
import logging
import os
import re
import shutil
from typing import Any

log = logging.getLogger(__name__)

ASSESSOR_TYPES = {
    "file_exists", "file_contains", "file_hash", "process_running",
    "port_listening", "log_contains", "wazuh_alert", "fim_change", "command_ran",
}

# target_vm 별 기본 로그 경로 (output_contains → log_contains 추론용).
_DEFAULT_LOG_PATHS = {
    "web": "/var/log/apache2/access.log",
    "siem": "/var/ossec/logs/alerts/alerts.json",
    "secu": "/var/log/syslog",
    "bastion": "/var/log/auth.log",
}

# 텍스트에서 파일/로그 경로 추출.
_PATH_RE = re.compile(r"/[\w./-]+\.(?:log|json|conf|txt|cfg)|/var/log/[\w./-]+")
# wazuh rule id (4~6자리 숫자).
_RULE_ID_RE = re.compile(r"\b(\d{4,6})\b")
# 포트 번호.
_PORT_RE = re.compile(r"\bport\s*[:=]?\s*(\d{1,5})|:(\d{2,5})\b")


def _candidate_text(mission: dict[str, Any]) -> str:
    """추론에 쓸 통합 텍스트 (expect + instruction + semantic)."""
    verify = mission.get("verify") or {}
    sem = verify.get("semantic") or {}
    parts: list[str] = [
        str(verify.get("expect") or ""),
        str(mission.get("instruction") or ""),
        str(mission.get("hint") or ""),
        str(sem.get("intent") or ""),
    ]
    parts.extend(str(x) for x in (sem.get("success_criteria") or []))
    return "\n".join(parts)


def _first_command_token(text: str) -> str | None:
    """명령 텍스트에서 첫 실행 도구 토큰 추출 (hydra, nft, nmap, curl ...)."""
    m = re.search(r"\b([a-z][a-z0-9_-]{1,20})\b", text.strip())
    return m.group(1) if m else None


def _pattern_for(mission: dict[str, Any]) -> str:
    """검사 패턴 — expect 우선, 없으면 명령 토큰/instruction 에서 도출."""
    verify = mission.get("verify") or {}
    expect = verify.get("expect")
    if isinstance(expect, list):
        expect = next((str(x) for x in expect if x), "")
    if expect:
        return str(expect)
    # expect 가 빈 미션(예: nftables 설정) — hint/instruction 의 명령 토큰.
    tok = _first_command_token(str(mission.get("hint") or "")) \
        or _first_command_token(str(mission.get("instruction") or ""))
    return tok or "*"


def _infer_type(target: str | None, text: str, verify: dict[str, Any]) -> str:
    low = text.lower()
    if (target == "siem") and any(k in low for k in ("alert", "wazuh", "ossec", "rule")):
        return "wazuh_alert"
    path_m = _PATH_RE.search(text)
    if path_m:
        p = path_m.group(0)
        if p.endswith((".log", ".json")) or "/var/log" in p or "alerts" in p:
            return "log_contains"
        return "file_contains"
    if "listen" in low or ("port" in low and "open" in low):
        return "port_listening"
    if "process" in low or "running" in low or "daemon" in low:
        return "process_running"
    # 기본: output_contains 는 "어떤 명령을 실행해 출력에 X 가 보였다" → command_ran
    return "command_ran"


def _params_for(ctype: str, mission: dict[str, Any], text: str) -> dict[str, Any]:
    verify = mission.get("verify") or {}
    target = mission.get("target_vm")
    pattern = _pattern_for(mission)

    if ctype == "file_exists":
        path = verify.get("path")
        if not path:
            m = _PATH_RE.search(text)
            path = m.group(0) if m else ""
        return {"path": path}
    if ctype == "file_contains":
        path = verify.get("path")
        if not path:
            m = _PATH_RE.search(text)
            path = m.group(0) if m else ""
        return {"path": path, "pattern": verify.get("pattern") or pattern}
    if ctype == "file_hash":
        return {"path": verify.get("path") or "", "algo": verify.get("algo") or "sha256",
                "expected": verify.get("expected") or ""}
    if ctype == "process_running":
        return {"name": verify.get("process") or verify.get("name") or pattern}
    if ctype == "port_listening":
        port = verify.get("port")
        if port is None:
            m = _PORT_RE.search(text)
            port = int(next((g for g in (m.groups() if m else []) if g), 0) or 0)
        return {"port": int(port or 0), "proto": verify.get("proto") or "tcp"}
    if ctype == "log_contains":
        path = verify.get("path")
        if not path:
            m = _PATH_RE.search(text)
            path = m.group(0) if m else _DEFAULT_LOG_PATHS.get(target or "", "/var/log/syslog")
        return {"path": path, "pattern": verify.get("pattern") or pattern}
    if ctype == "wazuh_alert":
        rule_id = verify.get("rule_id")
        if not rule_id:
            m = _RULE_ID_RE.search(text)
            rule_id = m.group(1) if m else None
        if rule_id:
            return {"rule_id": str(rule_id)}
        return {"pattern": pattern}
    if ctype == "fim_change":
        path = verify.get("path")
        if not path:
            m = _PATH_RE.search(text)
            path = m.group(0) if m else ""
        return {"path": path}
    # command_ran
    return {"pattern": verify.get("pattern") or pattern}


def compile_mission_checks(mission: dict[str, Any], *, side: str = "blue") -> list[dict[str, Any]]:
    """단일 미션 → check-spec[] (결정론, AI 0).

    이미 `verify.checks` 가 있으면 그대로 반환(캐시 우선).
    """
    verify = mission.get("verify") or {}
    cached = verify.get("checks")
    if isinstance(cached, list) and cached:
        return cached

    vtype = (verify.get("type") or "output_contains").lower()
    target = mission.get("target_vm")
    order = mission.get("order")
    text = _candidate_text(mission)

    if vtype in ASSESSOR_TYPES:
        ctype = vtype
    else:
        ctype = _infer_type(target, text, verify)

    params = _params_for(ctype, mission, text)
    cid = f"{side}-{order}-1"
    return [{"id": cid, "type": ctype, "target": target, "params": params}]


def cache_checks_into_mission(mission: dict[str, Any], *, side: str = "blue") -> list[dict[str, Any]]:
    """컴파일 결과를 mission['verify']['checks'] 에 캐시하고 반환 (멱등)."""
    verify = dict(mission.get("verify") or {})
    if isinstance(verify.get("checks"), list) and verify["checks"]:
        return verify["checks"]
    checks = compile_mission_checks(mission, side=side)
    verify["checks"] = checks
    mission["verify"] = verify
    return checks


def compile_side(missions: list[dict[str, Any]], *, side: str) -> list[dict[str, Any]]:
    """한 side 의 모든 미션을 컴파일해 각 미션에 캐시 + 전체 check-spec[] 반환."""
    out: list[dict[str, Any]] = []
    for m in missions or []:
        out.extend(cache_checks_into_mission(m, side=side))
    return out


# ──────────────────────────────────────────────────────
# (옵션) claude 1회 정제 — 시나리오 생성/dry-run 시점에만. 런타임 호출 금지.
# ──────────────────────────────────────────────────────
_CLAUDE_CMD = shutil.which("claude") or os.getenv("TUBEWAR_CLAUDE_BIN", "claude")
_CLAUDE_MODEL = os.getenv("TUBEWAR_CLAUDE_MODEL", "claude-haiku-4-5")
_CLAUDE_TIMEOUT = float(os.getenv("TUBEWAR_CLAUDE_TIMEOUT_SEC", "60"))

_REFINE_SYSTEM = """\
You convert a cyber-range mission's semantic intent into concrete, read-only
Assessor check specs. Allowed check types: file_exists, file_contains,
file_hash, process_running, port_listening, log_contains, wazuh_alert,
fim_change, command_ran. Each check: {"type","target","params"}. All checks are
READ-ONLY (no side effects). Return ONE JSON object: {"checks":[...]}.
"""


async def llm_refine_checks(mission: dict[str, Any], *, side: str = "blue") -> list[dict[str, Any]]:
    """semantic intent → 구체 check (claude 1회). 실패 시 결정론 fallback.

    **주의**: 시나리오 생성/dry-run 시점에만 사용. 런타임 채점에서 호출하지 말 것.
    """
    import asyncio
    deterministic = compile_mission_checks(mission, side=side)
    payload = {
        "instruction": mission.get("instruction"),
        "target_vm": mission.get("target_vm"),
        "verify": mission.get("verify"),
        "deterministic_guess": deterministic,
    }
    user = "## Mission\n```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```"
    try:
        proc = await asyncio.create_subprocess_exec(
            _CLAUDE_CMD, "-p", "--output-format", "json", "--model", _CLAUDE_MODEL,
            "--append-system-prompt", _REFINE_SYSTEM, user,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        out, _err = await asyncio.wait_for(proc.communicate(), timeout=_CLAUDE_TIMEOUT)
    except (asyncio.TimeoutError, FileNotFoundError):
        return deterministic
    if proc.returncode != 0:
        return deterministic
    try:
        wrap = json.loads(out.decode("utf-8", "replace"))
        result = wrap.get("result") or ""
        i, j = result.find("{"), result.rfind("}")
        parsed = json.loads(result[i:j + 1]) if i != -1 else {}
        checks = parsed.get("checks") or []
        # type 검증 + id 부여
        clean: list[dict[str, Any]] = []
        for n, c in enumerate(checks, start=1):
            if c.get("type") in ASSESSOR_TYPES:
                clean.append({
                    "id": f"{side}-{mission.get('order')}-{n}",
                    "type": c["type"],
                    "target": c.get("target") or mission.get("target_vm"),
                    "params": c.get("params") or {},
                })
        return clean or deterministic
    except Exception:
        return deterministic
