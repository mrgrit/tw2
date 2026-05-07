"""Phase 4 — battle 활성화 시 background 자동 모니터.

목표: 학생이 6v6 에서 공격/방어를 진행하면 tubewar 가 그 효과를 자동으로 관측해
BattleEvent 로 변환·점수 적용. 6v6 Bastion API `/exec` 의 안전 화이트리스트
(`curl http...`, `ping`, `nslookup`, `dig`) 만 사용한다.

현재 baseline:
  - 60s 간격으로 monitor heartbeat 이벤트 1회 (system, 0점)
  - 모든 blue 미션의 refined_expect 가 채워져 있으면, 표준 probe set 을 발사해
    expect 문자열이 응답에 포함되면 BLUE 점수 자동 부여 (mission.points)
  - 1회 매칭된 미션은 그 battle 내에서 dedupe (중복 가산 방지)

Real telemetry (Wazuh alerts.json tail, ModSec audit log) 통합은 Phase 6 의
work item — 6v6 Bastion API 가 read endpoint 를 제공하면 즉시 swap 가능하도록
PROBE_PLAYBOOK 만 데이터 영역에 분리한다.
"""
from __future__ import annotations
import asyncio
import logging
from typing import Any
import httpx

from ..db import SessionLocal
from ..models import Battle, BattleParticipant, Infra, Scenario
from . import battle_service as bs

log = logging.getLogger(__name__)

# infra 별 Bastion API /exec 안전 화이트리스트로 시도해볼 probe set.
# (각 probe 의 응답에서 미션 refined_expect 검색)
PROBE_PLAYBOOK: list[dict[str, str]] = [
    {"target": "web", "command": "curl http://10.20.30.80/"},
    {"target": "web", "command": "curl http://10.20.30.80/index.html"},
    {"target": "siem", "command": "curl http://10.20.30.100/"},
    {"target": "juiceshop", "command": "curl http://10.20.30.81/rest/products"},
]

POLL_INTERVAL_SEC = 15.0
HEARTBEAT_EVERY_N_TICKS = 4  # 60s

_tasks: dict[int, asyncio.Task] = {}
_seen_blue_hits: dict[int, set[int]] = {}   # battle_id → set(mission.order)


async def _exec_probe(infra: Infra, command: str) -> dict[str, Any]:
    port = (infra.port_map or {}).get("bastion_api", 9100)
    url = f"http://{infra.vm_ip}:{port}/exec"
    headers = {"X-API-Key": infra.bastion_api_key}
    body = {"target": "monitor", "command": command}
    try:
        async with httpx.AsyncClient(timeout=8.0) as c:
            r = await c.post(url, headers=headers, json=body)
            data = r.json() if "json" in r.headers.get("content-type", "") else {"text": r.text}
            return {"ok": r.status_code == 200, "status": r.status_code, **data}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def _refined_expects_from_blue(scenario: Scenario | None) -> list[tuple[int, int, str]]:
    """blue 미션 별 (order, points, refined_expect). dry_run 이 채운 refined 를 우선 사용."""
    if not scenario:
        return []
    missions = (scenario.mission_blue or {}).get("missions") or []
    dry = (scenario.scoring or {}).get("dry_run", {}) or {}
    refined_map: dict[int, str] = {}
    for r in (dry.get("review", {}) or {}).get("blue_review", []):
        order = r.get("order")
        ref = r.get("refined_expect", "") or ""
        if order is not None and ref:
            refined_map[int(order)] = ref

    out: list[tuple[int, int, str]] = []
    for m in missions:
        order = int(m.get("order") or 0)
        pts = int(m.get("points") or 0)
        expect = (
            refined_map.get(order)
            or ((m.get("verify") or {}).get("expect") or "")
        )
        if expect and pts:
            out.append((order, pts, expect))
    return out


async def _tick(battle_id: int, tick_idx: int) -> None:
    async with SessionLocal() as s:
        battle = await s.get(Battle, battle_id)
        if not battle or battle.status != "active":
            raise StopAsyncIteration
        from sqlalchemy import select
        participants = (await s.scalars(
            select(BattleParticipant).where(BattleParticipant.battle_id == battle_id)
        )).all()

        infras: list[Infra] = []
        for p in participants:
            if p.infra_id:
                inf = await s.get(Infra, p.infra_id)
                if inf:
                    infras.append(inf)

        scenario = await s.get(Scenario, battle.scenario_id) if battle.scenario_id else None

    # heartbeat
    if tick_idx % HEARTBEAT_EVERY_N_TICKS == 0:
        async with SessionLocal() as s:
            try:
                await bs.add_event(
                    s, battle_id=battle_id, actor_user_id=None,
                    event_type="system", target="monitor",
                    description="auto-monitor heartbeat",
                    points=0, detail={"tick": tick_idx, "infras": len(infras)},
                )
            except ValueError:
                # battle 이 그 사이 종료
                raise StopAsyncIteration

    if not infras or not scenario:
        return
    expects = _refined_expects_from_blue(scenario)
    if not expects:
        return

    # 첫 번째 infra 만 사용 (solo) — duel/ffa 는 monitoring 단순화 위해 같은 probe
    infra = infras[0]
    blue_user = None
    for p in participants:
        if p.role in ("blue", "solo"):
            blue_user = p.user_id
            break
    if blue_user is None:
        return

    seen = _seen_blue_hits.setdefault(battle_id, set())

    for probe in PROBE_PLAYBOOK:
        if seen and len(seen) >= len(expects):
            break  # 모든 미션 매칭 완료
        result = await _exec_probe(infra, probe["command"])
        body_text = (
            (result.get("stdout") or "")
            + (result.get("stderr") or "")
            + str(result.get("text") or "")
        )
        if not body_text:
            continue
        for (order, points, expect) in expects:
            if order in seen:
                continue
            if expect.lower() in body_text.lower():
                seen.add(order)
                async with SessionLocal() as s:
                    try:
                        await bs.add_event(
                            s, battle_id=battle_id, actor_user_id=blue_user,
                            event_type="detect", target=probe["target"],
                            description=f"auto-monitor matched blue #{order}: '{expect[:80]}'",
                            points=points,
                            detail={
                                "source": "auto_monitor",
                                "probe": probe["command"],
                                "matched_expect": expect,
                                "blue_mission_order": order,
                                "scenario_id": scenario.id,
                            },
                        )
                        log.info("auto-monitor battle=%s blue#%s matched +%s", battle_id, order, points)
                    except ValueError:
                        raise StopAsyncIteration


async def _loop(battle_id: int) -> None:
    log.info("auto-monitor START battle=%s", battle_id)
    tick = 0
    try:
        while True:
            tick += 1
            try:
                await _tick(battle_id, tick)
            except StopAsyncIteration:
                break
            except Exception:
                log.exception("auto-monitor tick error battle=%s", battle_id)
            await asyncio.sleep(POLL_INTERVAL_SEC)
    finally:
        _tasks.pop(battle_id, None)
        _seen_blue_hits.pop(battle_id, None)
        log.info("auto-monitor STOP battle=%s ticks=%s", battle_id, tick)


def start(battle_id: int) -> None:
    if battle_id in _tasks and not _tasks[battle_id].done():
        return
    t = asyncio.create_task(_loop(battle_id))
    _tasks[battle_id] = t


def stop(battle_id: int) -> None:
    t = _tasks.pop(battle_id, None)
    if t and not t.done():
        t.cancel()
    _seen_blue_hits.pop(battle_id, None)


def is_running(battle_id: int) -> bool:
    t = _tasks.get(battle_id)
    return bool(t and not t.done())
