"""Phase 9 — 채점 모델 추상화 (bastion vs claude).

목표: auto_monitor 와 hint endpoint 가 동일한 인터페이스로 두 모드를 호출.

토큰 절약 설계:
- `judge(probe_text, mission)` → 자연어 reasoning 만 LLM 호출.
  · probe_text 가 비어있으면 LLM 호출 X.
  · probe_text 의 SHA256 hash 가 동일 미션에 대해 마지막 호출과 같으면 cached reasoning 재사용.
- bastion 모드: 6v6 Bastion API 의 `/exec` 결과를 그대로 사용 (heuristic 매칭만, LLM 호출 X)
- claude 모드: probe diff 발생 시에만 Claude CLI subprocess 1회 호출.

cache 는 in-process dict — 서버 재시작 시 휘발 (의도적 — battle 종료 시 정리).
"""
from __future__ import annotations
import asyncio
import hashlib
import json
import logging
import os
import shutil
from dataclasses import dataclass

log = logging.getLogger(__name__)

_CLAUDE_CMD = shutil.which("claude") or "/usr/local/bin/claude"
_CLAUDE_MODEL = os.getenv("TUBEWAR_GRADER_MODEL", "claude-haiku-4-5")
_CLAUDE_TIMEOUT = float(os.getenv("TUBEWAR_GRADER_TIMEOUT", "30"))

# (battle_id, mission_order, probe_hash) → reasoning text
_judge_cache: dict[tuple[int, int, str], str] = {}


@dataclass(frozen=True)
class JudgeResult:
    matched: bool                 # 미션 expect 가 probe 응답에 포함되는가
    reasoning: str                # 자연어 채점 근거 (markdown 가능)
    model: str                    # 사용한 채점 모델 식별자
    cache_hit: bool = False
    cost_usd: float = 0.0


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "ignore")).hexdigest()[:16]


def _heuristic_match(probe_text: str, expect: str) -> bool:
    return bool(expect) and expect.lower() in probe_text.lower()


# ──────────────────────────────────────────────────────
# bastion 모드 — LLM 호출 없이 heuristic + 짧은 자연어 보고서
# ──────────────────────────────────────────────────────
def _bastion_reasoning(matched: bool, mission: dict, expect: str, probe_text: str) -> str:
    snippet = (probe_text or "").strip().replace("\n", " ")[:200]
    instr = mission.get("instruction") or mission.get("title") or "(미션 정보 없음)"
    if matched:
        return (
            f"**자동 채점 (bastion 휴리스틱)**\n\n"
            f"- 미션: {instr}\n"
            f"- 기대 패턴: `{expect}`\n"
            f"- 매칭됨 ✓ — probe 응답에서 패턴 발견\n"
            f"- 응답 발췌: `{snippet}`"
        )
    return (
        f"**자동 채점 (bastion 휴리스틱)**\n\n"
        f"- 미션: {instr}\n"
        f"- 기대 패턴: `{expect}`\n"
        f"- 미매칭 — probe 응답에 패턴 없음\n"
        f"- 응답 발췌: `{snippet or '(empty)'}`"
    )


# ──────────────────────────────────────────────────────
# claude 모드 — Claude CLI subprocess, json output, schema 강제
# ──────────────────────────────────────────────────────
_CLAUDE_SYSTEM = """\
You are a cyber-range judge. Decide whether a Blue mission has been satisfied
based on the probe response from the student's infrastructure.

Return ONE JSON object on a single line — no other text, no markdown fences:
{"matched": true|false,
 "reasoning": "<2~5문장 한국어 자연어 — 어떤 채점기준으로 어떻게 판단했는지>"}

Rules:
- 'matched' MUST be true ONLY if the probe response clearly satisfies the
  mission's expected outcome (e.g., a specific log entry, alert rule id, http
  status, response body marker).
- If probe response is empty or unrelated, set matched=false and explain why.
- Reasoning should reference the mission text, the expected pattern, and what
  was actually observed in the probe.
"""


async def _claude_judge(mission: dict, expect: str, probe_text: str) -> tuple[bool, str, float]:
    user = (
        f"## Mission\n```json\n{json.dumps(mission, ensure_ascii=False)}\n```\n"
        f"## Expected pattern\n`{expect}`\n"
        f"## Probe response (truncated 4KB)\n```\n{(probe_text or '')[:4000]}\n```"
    )
    try:
        proc = await asyncio.create_subprocess_exec(
            _CLAUDE_CMD, "-p", "--output-format", "json",
            "--model", _CLAUDE_MODEL,
            "--append-system-prompt", _CLAUDE_SYSTEM,
            user,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        out, err = await asyncio.wait_for(proc.communicate(), timeout=_CLAUDE_TIMEOUT)
    except asyncio.TimeoutError:
        return False, f"**채점 모델 timeout** (>{_CLAUDE_TIMEOUT}s)", 0.0
    except FileNotFoundError:
        return False, "**Claude CLI not found** — claude binary 가 PATH 에 없음", 0.0

    if proc.returncode != 0:
        return False, f"**Claude CLI exit {proc.returncode}**: {err.decode('utf-8','replace')[:300]}", 0.0

    try:
        wrap = json.loads(out.decode("utf-8", "replace"))
    except json.JSONDecodeError:
        return False, "**Claude CLI: 응답 JSON 파싱 실패**", 0.0
    cost = float(wrap.get("total_cost_usd") or 0.0)
    text = (wrap.get("result") or "").strip()
    # result 가 단일 JSON line 이어야
    try:
        # 가끔 모델이 fence 를 붙이면 strip
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        parsed = json.loads(text)
        return bool(parsed.get("matched")), str(parsed.get("reasoning") or ""), cost
    except Exception:
        return _heuristic_match(probe_text, expect), \
               f"**판정 raw**\n```\n{text[:500]}\n```", cost


# ──────────────────────────────────────────────────────
# 통합 진입
# ──────────────────────────────────────────────────────
async def judge(
    *, monitor: str, battle_id: int, mission: dict, expect: str, probe_text: str,
) -> JudgeResult:
    order = int(mission.get("order") or 0)
    h = _hash(probe_text or "")
    key = (battle_id, order, h)
    if key in _judge_cache:
        cached = _judge_cache[key]
        # cached 가 matched 였는지 reconstruct — 캐시는 reasoning 만 저장하니
        # heuristic 으로 재계산 (cheap)
        matched = _heuristic_match(probe_text, expect)
        return JudgeResult(matched=matched, reasoning=cached, model=monitor + ":cache",
                           cache_hit=True, cost_usd=0.0)

    if monitor == "claude":
        matched, reasoning, cost = await _claude_judge(mission, expect, probe_text)
        _judge_cache[key] = reasoning
        return JudgeResult(matched=matched, reasoning=reasoning, model=_CLAUDE_MODEL,
                           cache_hit=False, cost_usd=cost)

    # bastion (default) — LLM 안 씀, heuristic + short report
    matched = _heuristic_match(probe_text, expect)
    reasoning = _bastion_reasoning(matched, mission, expect, probe_text)
    _judge_cache[key] = reasoning
    return JudgeResult(matched=matched, reasoning=reasoning, model="bastion-heuristic",
                       cache_hit=False, cost_usd=0.0)


def clear_cache(battle_id: int) -> None:
    keys = [k for k in _judge_cache if k[0] == battle_id]
    for k in keys:
        _judge_cache.pop(k, None)
