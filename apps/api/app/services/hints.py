"""Phase 9 — 학생 명시 요청 시 LLM 이 생성하는 힌트.

토큰 절약 설계:
- per-(battle, user) 60s cooldown — 스팸 방지
- (battle, mission_side, mission_order, last_event_id) cache — 같은 상태에선 LLM 재호출 X
- battle.hint_enabled=False 시 cooldown 검사 전에 거부
- monitor 모드 (bastion vs claude) 와 동일한 모델 선택 — bastion 모드에선 LLM 안 쓰고 시나리오에서
  추출한 정적 힌트만 반환 (비용 0)
"""
from __future__ import annotations
import asyncio
import json
import logging
import os
import shutil
import time
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Battle, BattleEvent, BattleHint, Scenario

log = logging.getLogger(__name__)

_CLAUDE_CMD = shutil.which("claude") or "/usr/local/bin/claude"
_CLAUDE_MODEL = os.getenv("TUBEWAR_HINT_MODEL", "claude-haiku-4-5")
_CLAUDE_TIMEOUT = float(os.getenv("TUBEWAR_HINT_TIMEOUT", "30"))
COOLDOWN_SEC = float(os.getenv("TUBEWAR_HINT_COOLDOWN", "60"))

# (battle_id, user_id) → last_request_monotonic
_last_request: dict[tuple[int, int], float] = {}


@dataclass
class HintResult:
    text: str
    model: str
    cache_hit: bool
    cost_usd: float


def cooldown_remaining(battle_id: int, user_id: int) -> float:
    last = _last_request.get((battle_id, user_id))
    if last is None:
        return 0.0
    return max(0.0, COOLDOWN_SEC - (time.monotonic() - last))


def _mark(battle_id: int, user_id: int) -> None:
    _last_request[(battle_id, user_id)] = time.monotonic()


def _bastion_static_hint(mission_side: str, missions: list[dict], events_so_far: list[dict]) -> str:
    """LLM 호출 없이 시나리오 텍스트로부터 진행 단계 안내."""
    completed_targets = {(e.get("event_type"), e.get("target")) for e in events_so_far if e.get("points")}
    side_label = "공격(Red)" if mission_side == "red" else "방어(Blue)" if mission_side == "blue" else "전체"
    if not missions:
        return f"**{side_label} 힌트 (bastion 정적)**\n\n시나리오에 미션이 없습니다."

    # order 가 작은 미션 중 아직 안 한 것
    todo = []
    for m in sorted(missions, key=lambda x: x.get("order", 99)):
        instr = (m.get("instruction") or m.get("title") or "").strip()
        target = m.get("target_vm") or m.get("target") or ""
        # heuristic: 이 미션 target 으로 매칭되는 점수 이벤트가 이미 있나
        already = any(t for (_et, t) in completed_targets if t and target and t.lower() in target.lower())
        if not already:
            todo.append(m)
        if len(todo) >= 2:
            break

    if not todo:
        return f"**{side_label} 힌트 (bastion 정적)**\n\n모든 주요 미션에 대한 점수 이벤트가 이미 기록된 것으로 보입니다. 새로운 시도가 필요하면 미션 instruction 을 다시 확인하세요."

    parts = [f"**{side_label} 힌트 (bastion 정적)**", ""]
    for m in todo:
        order = m.get("order")
        instr = (m.get("instruction") or m.get("title") or "")[:200]
        target = m.get("target_vm") or m.get("target") or "-"
        verify = (m.get("verify") or {}).get("expect") or "-"
        parts.append(f"- 미션 #{order} (target=`{target}`)")
        parts.append(f"  - 할 일: {instr}")
        parts.append(f"  - 성공 조건: `{verify}`")
    parts.append("")
    parts.append("_LLM 호출 없이 시나리오 텍스트만 사용한 힌트입니다 — 더 깊은 가이드가 필요하면 monitor=claude 로 공방전을 다시 만들거나 admin 에게 요청하세요._")
    return "\n".join(parts)


_CLAUDE_SYSTEM = """\
You are an attentive cyber-range coach helping a student progress in an
ongoing red/blue exercise. Reply in Korean (한국어). Keep the hint focused —
NEVER reveal full exploit payloads, working passwords, or copy-paste solutions.
Instead:

- Identify the *first concrete next action* the student should take, given:
  the scenario missions for their side, what events they have already produced,
  and their stated stuck-point.
- Reference the relevant 6v6 component (juiceshop, dvwa, neobank, mediforum,
  govportal, aicompanion, adminconsole, web/siem) so the student knows where
  to focus.
- 4~8문장 정도. 마크다운 사용 가능. 미션 번호를 명시.
"""


async def _claude_hint(prompt: str) -> tuple[str, float]:
    try:
        proc = await asyncio.create_subprocess_exec(
            _CLAUDE_CMD, "-p", "--output-format", "json",
            "--model", _CLAUDE_MODEL,
            "--append-system-prompt", _CLAUDE_SYSTEM,
            prompt,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        out, err = await asyncio.wait_for(proc.communicate(), timeout=_CLAUDE_TIMEOUT)
    except asyncio.TimeoutError:
        return f"**힌트 모델 timeout** (>{_CLAUDE_TIMEOUT}s)", 0.0
    except FileNotFoundError:
        return "**Claude CLI not found** — claude binary 가 PATH 에 없음", 0.0
    if proc.returncode != 0:
        return f"**Claude CLI exit {proc.returncode}**: {err.decode('utf-8','replace')[:300]}", 0.0
    try:
        wrap = json.loads(out.decode("utf-8", "replace"))
    except json.JSONDecodeError:
        return "**Claude CLI: JSON 파싱 실패**", 0.0
    return (wrap.get("result") or "").strip(), float(wrap.get("total_cost_usd") or 0.0)


async def request_hint(
    session: AsyncSession,
    *,
    battle: Battle,
    user_id: int,
    mission_side: str = "any",   # red | blue | any
    note: str = "",
) -> HintResult:
    if not battle.hint_enabled:
        raise ValueError("hint disabled for this battle")
    if battle.status != "active":
        raise ValueError("battle is not active")

    remaining = cooldown_remaining(battle.id, user_id)
    if remaining > 0:
        raise ValueError(f"cooldown {remaining:.0f}s remaining")

    # 캐시 키 = (battle_id, side, last_event_id) — 새 이벤트 없으면 같은 힌트 반환
    last_event_id = await session.scalar(
        select(BattleEvent.id).where(BattleEvent.battle_id == battle.id)
        .order_by(BattleEvent.id.desc()).limit(1)
    ) or 0
    probe_hash = f"side={mission_side}|last_event={last_event_id}"

    cached = await session.scalar(
        select(BattleHint).where(
            BattleHint.battle_id == battle.id,
            BattleHint.mission_side == mission_side,
            BattleHint.probe_hash == probe_hash,
        ).order_by(BattleHint.id.desc()).limit(1)
    )
    if cached:
        _mark(battle.id, user_id)
        return HintResult(text=cached.text, model=cached.model + ":cache",
                          cache_hit=True, cost_usd=0.0)

    # 시나리오 + 진행 이벤트 로드
    scenario = await session.get(Scenario, battle.scenario_id) if battle.scenario_id else None
    missions: list[dict] = []
    if scenario:
        if mission_side in ("red", "any"):
            missions += [{**m, "_side": "red"} for m in (scenario.mission_red or {}).get("missions", []) or []]
        if mission_side in ("blue", "any"):
            missions += [{**m, "_side": "blue"} for m in (scenario.mission_blue or {}).get("missions", []) or []]

    events_rows = (await session.scalars(
        select(BattleEvent).where(BattleEvent.battle_id == battle.id)
        .order_by(BattleEvent.id.desc()).limit(20)
    )).all()
    events_summary = [
        {"event_type": e.event_type, "target": e.target, "points": e.points,
         "description": (e.description or "")[:120]}
        for e in events_rows
    ]

    if battle.monitor == "claude":
        prompt = (
            f"## 시나리오: {scenario.title if scenario else '(미정)'}\n"
            f"## 학생이 보는 미션 ({mission_side})\n"
            f"```json\n{json.dumps(missions, ensure_ascii=False)[:3000]}\n```\n"
            f"## 최근 이벤트 (최대 20개)\n"
            f"```json\n{json.dumps(events_summary, ensure_ascii=False)[:1500]}\n```\n"
            f"## 학생 메모\n{note or '(없음)'}\n\n"
            "위를 보고 학생이 *지금 당장 해볼 수 있는 가장 작은 한 발짝* 을 짚어줘."
        )
        text, cost = await _claude_hint(prompt)
        model = _CLAUDE_MODEL
    else:
        text = _bastion_static_hint(mission_side, missions, events_summary)
        cost = 0.0
        model = "bastion-static"

    row = BattleHint(
        battle_id=battle.id, requested_by=user_id, mission_side=mission_side,
        mission_order=None, probe_hash=probe_hash,
        text=text, model=model, cost_usd=int(round(cost * 10000)),  # micro-cents
    )
    session.add(row)
    await session.commit()
    _mark(battle.id, user_id)
    return HintResult(text=text, model=model, cache_hit=False, cost_usd=cost)
