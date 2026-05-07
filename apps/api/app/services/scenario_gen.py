"""자연어 + lecture.md 컨텍스트 → battle scenario draft 생성.

호출 매커니즘: `claude -p --output-format json [--model ...]` subprocess.
이 방식은 사용자 인터랙티브 세션과 동일한 인증을 재사용 (env ANTHROPIC_API_KEY 불필요).

응답 schema (모델이 반드시 이 JSON 만 출력):

{
  "title": str,
  "description": str,
  "difficulty": "easy" | "medium" | "hard",
  "time_limit_sec": int (600..7200),
  "battle_type_hint": "1v1" | "ffa" | "solo",
  "red_missions": [{"order": int, "instruction": str, "hint": str, "points": int, "target_vm": str, "verify": {...}}],
  "blue_missions": [{...same shape...}]
}

후처리: pydantic 으로 검증 → DB Scenario INSERT (status=draft, source=claude).
실패 시 ScenarioGenerationError. CLI 미설치/auth 실패는 즉시 예외.

운영 옵션:
- env TUBEWAR_CLAUDE_BIN (default: 'claude')
- env TUBEWAR_CLAUDE_MODEL (default: 'claude-haiku-4-5'  ← 비용 절감)
- env TUBEWAR_CLAUDE_TIMEOUT_SEC (default: 180)
"""
from __future__ import annotations
import asyncio
import json
import logging
import os
import re
from typing import Any
from pydantic import BaseModel, Field, ValidationError

from .lecture_context import build_context_block, parse_week_range

log = logging.getLogger(__name__)


class ScenarioGenerationError(RuntimeError):
    pass


# ── 출력 schema ────────────────────────────────────
class _Verify(BaseModel):
    type: str = Field(default="output_contains")
    expect: str = Field(default="")


class _Mission(BaseModel):
    order: int
    instruction: str
    hint: str = ""
    points: int = Field(ge=1, le=100)
    target_vm: str = Field(default="attacker")
    verify: dict[str, Any] = Field(default_factory=lambda: {"type": "output_contains", "expect": ""})


class GeneratedScenario(BaseModel):
    title: str = Field(min_length=4, max_length=200)
    description: str = Field(min_length=20, max_length=4000)
    difficulty: str = Field(pattern=r"^(easy|medium|hard)$")
    time_limit_sec: int = Field(ge=600, le=7200)
    battle_type_hint: str = Field(pattern=r"^(1v1|ffa|solo)$", default="1v1")
    red_missions: list[_Mission] = Field(min_length=2, max_length=10)
    blue_missions: list[_Mission] = Field(min_length=2, max_length=10)


# ── 프롬프트 ───────────────────────────────────────
_SYSTEM_TEMPLATE = """\
You are tubewar's scenario factory. Given a course context and the admin's
natural-language request, you produce ONE battle scenario suitable for
two students battling over their 6v6 lab infrastructures (single-VM
docker-compose with these containers reachable from the attacker
container at 10.20.30.202):

  - secu  10.20.30.1   nftables + Suricata (+ Wazuh agent)
  - web   10.20.30.80  Apache + ModSecurity reverse proxy
  - juiceshop  10.20.30.81   OWASP Juice Shop
  - dvwa       10.20.30.82
  - neobank    10.20.30.83
  - govportal  10.20.30.84
  - mediforum  10.20.30.85
  - adminconsole 10.20.30.86  (RCE/XXE/SSRF)
  - aicompanion  10.20.30.87  (LLM abuse)
  - siem  10.20.30.100 Wazuh manager
  - bastion 10.20.30.201 SSH jump + Bastion API :9100
  - attacker 10.20.30.202 nmap/sqlmap/hydra/nikto/etc

Hard requirements:
1. Output ONLY a single JSON object. No prose, no markdown, no code fence.
2. Match the schema exactly:
   {"title": str, "description": str, "difficulty": "easy|medium|hard",
    "time_limit_sec": int, "battle_type_hint": "1v1|ffa|solo",
    "red_missions": [...], "blue_missions": [...]}
3. Each mission: {"order": int, "instruction": str, "hint": str,
   "points": int (1..100), "target_vm": str, "verify": {"type": "output_contains", "expect": str}}.
4. Red and Blue missions MUST mirror in scope — for each red mission,
   blue should have a corresponding detection/blocking mission.
5. Cite concrete commands (sqlmap/nmap/curl/grep) and concrete log
   paths (`/var/ossec/logs/alerts/alerts.json`, ModSec audit log) where
   applicable. Use IPs above, not placeholders.
6. 4-6 missions per side. total time_limit_sec sane (1800-3600 typical).
7. Korean is fine for instruction/hint/description but JSON keys stay English.
"""

_USER_TEMPLATE = """\
Course context (CCC lecture excerpts):
{context}

Admin request: {request}

Now produce the JSON object only.
"""


def build_prompt(*, request: str, context: str) -> tuple[str, str]:
    return _SYSTEM_TEMPLATE, _USER_TEMPLATE.format(context=context, request=request)


# ── claude CLI 호출 ────────────────────────────────
async def _invoke_claude(system: str, user: str) -> dict[str, Any]:
    bin_ = os.environ.get("TUBEWAR_CLAUDE_BIN", "claude")
    model = os.environ.get("TUBEWAR_CLAUDE_MODEL", "claude-haiku-4-5")
    timeout = float(os.environ.get("TUBEWAR_CLAUDE_TIMEOUT_SEC", "180"))

    full = f"{system}\n\n{user}"
    cmd = [bin_, "-p", "--output-format", "json", "--model", model]
    log.info("invoking claude CLI: model=%s prompt_chars=%d", model, len(full))

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as e:
        raise ScenarioGenerationError(f"claude CLI not found: {e}") from e

    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(full.encode("utf-8")), timeout=timeout
        )
    except asyncio.TimeoutError:
        proc.kill()
        raise ScenarioGenerationError(f"claude CLI timed out after {timeout}s")

    if proc.returncode != 0:
        raise ScenarioGenerationError(
            f"claude CLI exited {proc.returncode}: {stderr.decode('utf-8','replace')[:500]}"
        )

    try:
        return json.loads(stdout.decode("utf-8"))
    except json.JSONDecodeError as e:
        raise ScenarioGenerationError(f"claude CLI returned non-JSON: {e}; head={stdout[:200]!r}")


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def _extract_json_object(text: str) -> dict[str, Any]:
    """모델이 가끔 fence 를 붙이거나 prose 를 섞을 수 있으므로 robust 추출."""
    text = text.strip()
    m = _FENCE_RE.search(text)
    if m:
        text = m.group(1).strip()
    if not text.startswith("{"):
        # 첫 { 부터 마지막 } 까지 잘라보기
        i, j = text.find("{"), text.rfind("}")
        if i == -1 or j == -1 or j < i:
            raise ScenarioGenerationError(f"no JSON object in model output: {text[:200]!r}")
        text = text[i : j + 1]
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ScenarioGenerationError(f"model output not parseable JSON: {e}; head={text[:200]!r}")


# ── 공개 entrypoint ────────────────────────────────
async def generate_scenario(
    *, request: str, course_ref: str | None = None, weeks_spec: str | None = None,
) -> tuple[GeneratedScenario, dict[str, Any]]:
    """자연어 + (옵션) course/주차 spec → 검증된 GeneratedScenario.

    반환: (scenario, meta) where meta carries {duration_ms, model, cost_usd, lecture_chars}.
    """
    weeks = parse_week_range(weeks_spec) if weeks_spec else []
    if course_ref and weeks:
        context = build_context_block(course_ref, weeks)
    else:
        context = "(no course context provided — admin asked freeform)"

    system, user = build_prompt(request=request, context=context)
    raw = await _invoke_claude(system, user)

    if raw.get("is_error") or raw.get("subtype") != "success":
        msg = raw.get("api_error_status") or raw.get("result") or "unknown error"
        raise ScenarioGenerationError(f"claude returned error: {msg}")

    text = raw.get("result", "")
    if not text:
        raise ScenarioGenerationError("claude returned empty result")
    parsed = _extract_json_object(text)

    try:
        scenario = GeneratedScenario.model_validate(parsed)
    except ValidationError as e:
        raise ScenarioGenerationError(f"generated scenario failed schema validation: {e}")

    meta = {
        "duration_ms": raw.get("duration_ms"),
        "model_usage": raw.get("modelUsage", {}),
        "cost_usd": raw.get("total_cost_usd"),
        "lecture_chars": len(context),
        "course_ref": course_ref,
        "weeks": weeks,
    }
    return scenario, meta
