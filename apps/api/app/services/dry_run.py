"""Phase 4 — 시나리오 미션 정합성 자동 검증.

Claude (haiku) 가 각 red/blue 미션을 다음 4축으로 평가한다:
  1) is_plausible — instruction 이 6v6 환경에서 실제로 시도 가능한가
  2) refined_expect — verify.expect 를 더 정확한 substring 으로 다듬음
  3) confidence — 0..1
  4) notes — 사람용 메모 (실패 시 보완 포인트)

이후 옵션으로 6v6 Bastion API `/exec` 를 통해 안전 화이트리스트 명령
(curl http..., ping ..., nslookup ...) 을 1~2회 발사해 reachability 만
확인한다. 실 실행 결과는 dry_run.executor.probes 에 누적.

성공 기준: 미션의 70% 이상이 is_plausible=true → Scenario.status = validated.
미만이면 draft 유지 + notes 첨부.
"""
from __future__ import annotations
import json
import logging
import os
import re
from typing import Any
import httpx
from pydantic import BaseModel, Field, ValidationError

from .scenario_gen import _invoke_claude  # subprocess wrapper

log = logging.getLogger(__name__)


# ── Claude 출력 schema ──────────────────────────────
class _MissionReview(BaseModel):
    order: int
    is_plausible: bool
    refined_expect: str = Field(default="", max_length=400)
    confidence: float = Field(ge=0.0, le=1.0)
    notes: str = Field(default="", max_length=1000)


class ScenarioReview(BaseModel):
    summary: str
    red_review: list[_MissionReview]
    blue_review: list[_MissionReview]
    overall_pass_rate: float = Field(ge=0.0, le=1.0)


# ── 프롬프트 ────────────────────────────────────────
_REVIEW_SYSTEM = """\
You are tubewar's mission auditor. The 6v6 lab baseline (single-VM
docker-compose) is:
  - secu        10.20.30.1     nftables + Suricata + Wazuh agent
  - web         10.20.30.80    Apache + ModSecurity reverse proxy
  - juiceshop   10.20.30.81    OWASP Juice Shop
  - dvwa        10.20.30.82
  - neobank     10.20.30.83    Flask, 30 vulnerabilities
  - govportal   10.20.30.84    Flask, 25 vulnerabilities
  - mediforum   10.20.30.85    Flask
  - adminconsole 10.20.30.86   Flask (RCE / XXE / SSRF / pickle)
  - aicompanion 10.20.30.87    OWASP LLM Top 10 targets (mock LLM ok)
  - siem        10.20.30.100   Wazuh manager
  - bastion     10.20.30.201   SSH jump + Bastion API :9100
  - attacker    10.20.30.202   nmap / hydra / sqlmap / nikto

Evaluate every red and blue mission against this baseline.

For each mission produce:
- order: int (mission order)
- is_plausible: true if a competent student can execute it on a fresh 6v6
- refined_expect: shorter, more reliable substring (or regex literal) than
  the verify.expect originally provided. Pick something a real successful
  run would print verbatim — e.g. "200 OK" / "available techniques" /
  "rule_id":"31108" / "MODSECURITY". Empty string if you cannot improve it.
- confidence: 0.0 (very iffy) .. 1.0 (battle-tested)
- notes: short Korean note for the admin (problems, alternative commands)

Return ONE JSON object only, no markdown:
{
  "summary": str,
  "red_review": [...],
  "blue_review": [...],
  "overall_pass_rate": float
}
"""


def _build_review_prompt(scenario: dict[str, Any]) -> tuple[str, str]:
    user = (
        f"Scenario title: {scenario.get('title')}\n"
        f"Description: {scenario.get('description', '')[:600]}\n\n"
        f"red_missions:\n{json.dumps(scenario.get('mission_red', {}), ensure_ascii=False)[:6000]}\n\n"
        f"blue_missions:\n{json.dumps(scenario.get('mission_blue', {}), ensure_ascii=False)[:6000]}\n\n"
        "Audit and return JSON."
    )
    return _REVIEW_SYSTEM, user


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def _extract_json(text: str) -> dict[str, Any]:
    m = _FENCE.search(text)
    if m:
        text = m.group(1).strip()
    if not text.strip().startswith("{"):
        i, j = text.find("{"), text.rfind("}")
        if i == -1 or j == -1:
            raise ValueError(f"no JSON: {text[:200]!r}")
        text = text[i : j + 1]
    return json.loads(text)


# ── Reachability probe (옵션) ─────────────────────
async def _probe_via_bastion(infra) -> list[dict]:
    """6v6 Bastion API /exec 안전 화이트리스트로 cheap probes 실행."""
    if not infra:
        return [{"check": "skip", "reason": "no infra"}]
    port = (infra.port_map or {}).get("bastion_api", 9100)
    base = f"http://{infra.vm_ip}:{port}"
    headers = {"X-API-Key": infra.bastion_api_key}
    probes = [
        {"target": "web", "command": "curl http://10.20.30.80/"},
        {"target": "siem", "command": "curl http://10.20.30.100/"},
    ]
    out: list[dict] = []
    try:
        async with httpx.AsyncClient(timeout=8.0) as c:
            for p in probes:
                try:
                    r = await c.post(f"{base}/exec", headers=headers, json=p)
                    out.append({
                        "command": p["command"], "rc": r.status_code,
                        "body_head": r.text[:200],
                    })
                except Exception as e:
                    out.append({"command": p["command"], "error": f"{type(e).__name__}: {e}"})
    except Exception as e:
        out.append({"check": "exec-skipped", "error": f"{type(e).__name__}: {e}"})
    return out


# ── 공개 API ────────────────────────────────────────
async def review_scenario(scenario: dict[str, Any], infra=None) -> dict[str, Any]:
    """LLM 기반 정합성 검증 + (옵션) reachability probe.

    반환 dict shape:
      {
        "summary": str,
        "review": ScenarioReview.dict(),
        "passed": bool,
        "executor": {"probes": [...]} (optional),
      }
    """
    system, user = _build_review_prompt(scenario)
    raw = await _invoke_claude(system, user)
    if raw.get("is_error") or raw.get("subtype") != "success":
        return {
            "summary": "claude call failed",
            "passed": False,
            "error": raw.get("api_error_status") or "unknown",
        }
    try:
        text = raw.get("result", "")
        parsed = _extract_json(text)
        review = ScenarioReview.model_validate(parsed)
    except (ValueError, ValidationError) as e:
        return {
            "summary": "review JSON unparseable",
            "passed": False,
            "error": str(e),
            "raw_head": text[:300] if 'text' in dir() else "",
        }

    passed = review.overall_pass_rate >= 0.7

    out: dict[str, Any] = {
        "summary": review.summary,
        "passed": passed,
        "pass_rate": review.overall_pass_rate,
        "review": review.model_dump(),
        "claude_meta": {
            "duration_ms": raw.get("duration_ms"),
            "cost_usd": raw.get("total_cost_usd"),
        },
    }

    if infra is not None:
        try:
            out["executor"] = {"probes": await _probe_via_bastion(infra)}
        except Exception as e:
            out["executor"] = {"error": f"{type(e).__name__}: {e}"}

    return out
