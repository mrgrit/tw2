"""Phase 4 + 9 + 9.1 — battle 활성화 시 background 자동 모니터.

목표: 학생이 6v6 에서 공격/방어를 진행하면 tubewar 가 그 효과를 자동으로 관측해
BattleEvent 로 변환·점수 적용. 6v6 Bastion API `/exec` 의 안전 화이트리스트
(`curl http...`, `ping`, `nslookup`, `dig`) 만 사용한다.

Phase 9 보강:
- battle.target_apps 로 probe set 을 좁힘 (선택된 앱만 점검 — token + 시간 절약)
- battle.monitor 모드별 (bastion / claude) 로 grader 분기. claude 일 때는 probe diff
  발생 시에만 Claude CLI 1회 호출 (probe_hash 캐시).
- 매 score 부여마다 BattleEvent.reasoning 자연어 채점 근거 첨부.
- solved 미션은 그 battle 내에서 dedupe (기존 동작 유지).
- probe 응답이 직전과 동일하면 (probe_hash) LLM 미호출.
"""
from __future__ import annotations
import asyncio
import hashlib
import logging
from typing import Any
import httpx

import datetime as dt
from sqlalchemy import select

from ..db import SessionLocal
from ..models import Battle, BattleEvent, BattleParticipant, Infra, Scenario
from . import battle_service as bs, grader

log = logging.getLogger(__name__)

# 6v6 의 8 앱 → probe spec (target alias + Bastion API /exec 화이트리스트 명령)
APP_PROBES: dict[str, list[dict[str, str]]] = {
    "web":          [{"target": "web", "command": "curl http://10.20.30.80/"}],
    "juiceshop":    [{"target": "juiceshop", "command": "curl http://10.20.30.81/rest/products"}],
    "dvwa":         [{"target": "dvwa", "command": "curl http://10.20.30.82/"}],
    "neobank":      [{"target": "neobank", "command": "curl http://10.20.30.83/"}],
    "mediforum":    [{"target": "mediforum", "command": "curl http://10.20.30.84/"}],
    "govportal":    [{"target": "govportal", "command": "curl http://10.20.30.85/"}],
    "aicompanion":  [{"target": "aicompanion", "command": "curl http://10.20.30.86/"}],
    "adminconsole": [{"target": "adminconsole", "command": "curl http://10.20.30.87/"}],
}
# target_apps 가 비었을 때 사용할 default — 가장 자주 쓰이는 4개 + siem
DEFAULT_PROBES: list[dict[str, str]] = [
    {"target": "web", "command": "curl http://10.20.30.80/"},
    {"target": "juiceshop", "command": "curl http://10.20.30.81/rest/products"},
    {"target": "siem", "command": "curl http://10.20.30.100/"},
]

POLL_INTERVAL_SEC = 15.0
HEARTBEAT_EVERY_N_TICKS = 4  # 60s

_tasks: dict[int, asyncio.Task] = {}
_seen_blue_hits: dict[int, set[int]] = {}   # battle_id → set(mission.order)
_last_probe_hash: dict[tuple[int, str], str] = {}   # (battle_id, probe.cmd) → sha256


def _hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8", "ignore")).hexdigest()[:16]


def _resolve_probes(target_apps: list[str]) -> list[dict[str, str]]:
    if not target_apps:
        return DEFAULT_PROBES
    out: list[dict[str, str]] = []
    for app in target_apps:
        out.extend(APP_PROBES.get(app, []))
    return out or DEFAULT_PROBES


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


def _refined_expects_from_blue(scenario: Scenario | None) -> list[tuple[int, int, str, dict]]:
    """blue 미션 별 (order, points, refined_expect, raw_mission). dry_run 이 채운 refined 우선."""
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

    out: list[tuple[int, int, str, dict]] = []
    for m in missions:
        order = int(m.get("order") or 0)
        pts = int(m.get("points") or 0)
        expect = (
            refined_map.get(order)
            or ((m.get("verify") or {}).get("expect") or "")
        )
        if expect and pts:
            out.append((order, pts, expect, m))
    return out


async def _tick(battle_id: int, tick_idx: int) -> None:
    async with SessionLocal() as s:
        battle = await s.get(Battle, battle_id)
        if not battle or battle.status != "active":
            raise StopAsyncIteration
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
        target_apps = list(battle.target_apps or [])
        monitor_mode = battle.monitor or "bastion"

    # heartbeat — 60s 마다. 변화 없으면 직전 heartbeat row 를 UPDATE 해서 시간 범위만 늘림
    if tick_idx % HEARTBEAT_EVERY_N_TICKS == 0:
        async with SessionLocal() as s:
            try:
                await _emit_heartbeat(
                    s, battle_id=battle_id, monitor_mode=monitor_mode,
                    infras_count=len(infras), target_apps=target_apps, tick_idx=tick_idx,
                )
            except ValueError:
                raise StopAsyncIteration

    if not infras or not scenario:
        return
    expects = _refined_expects_from_blue(scenario)
    if not expects:
        return

    infra = infras[0]
    blue_user = None
    for p in participants:
        if p.role in ("blue", "solo", "free"):
            blue_user = p.user_id
            break
    if blue_user is None:
        return

    seen = _seen_blue_hits.setdefault(battle_id, set())
    probes = _resolve_probes(target_apps)

    for probe in probes:
        if seen and len(seen) >= len(expects):
            break

        result = await _exec_probe(infra, probe["command"])
        body_text = (
            (result.get("stdout") or "")
            + (result.get("stderr") or "")
            + str(result.get("text") or "")
        )
        if not body_text:
            continue

        # token-saver: probe 응답이 직전과 동일하면 LLM 호출 스킵
        new_hash = _hash(body_text)
        prev_hash = _last_probe_hash.get((battle_id, probe["command"]))
        unchanged = prev_hash is not None and prev_hash == new_hash
        _last_probe_hash[(battle_id, probe["command"])] = new_hash

        for (order, points, expect, mission) in expects:
            if order in seen:
                continue
            # heuristic 매칭이 false 면 grader 호출도 안 함 (정답 가능성 0 으로 간주)
            if expect.lower() not in body_text.lower():
                continue

            # 매칭 후보 — 동일 응답이면 LLM 안 쓰고 휴리스틱 reasoning 으로 처리
            effective_monitor = "bastion" if unchanged else monitor_mode
            verdict = await grader.judge(
                monitor=effective_monitor, battle_id=battle_id,
                mission=mission, expect=expect, probe_text=body_text,
            )
            if not verdict.matched:
                continue

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
                            "monitor": effective_monitor,
                            "model": verdict.model,
                            "cache_hit": verdict.cache_hit,
                            "cost_usd": verdict.cost_usd,
                            "probe_hash": new_hash,
                        },
                        reasoning=verdict.reasoning,
                    )
                    log.info(
                        "auto-monitor battle=%s blue#%s matched +%s mode=%s cache=%s cost=%.4f",
                        battle_id, order, points, effective_monitor, verdict.cache_hit, verdict.cost_usd,
                    )
                except ValueError:
                    raise StopAsyncIteration


def _fmt_korean_time(d: dt.datetime) -> str:
    """오전/오후 H시 MM분 — heartbeat 표시용 (서버 KST 가정. 환경별로 다르면 그냥 24시간)."""
    try:
        local = d.astimezone()  # 서버 로컬 타임존
    except Exception:
        local = d
    h = local.hour
    am = "오전" if h < 12 else "오후"
    h12 = h % 12 or 12
    return f"{am} {h12}시 {local.minute:02d}분"


async def _emit_heartbeat(
    session, *, battle_id: int, monitor_mode: str,
    infras_count: int, target_apps: list[str], tick_idx: int,
) -> None:
    """heartbeat 이벤트 — 직전 이벤트가 같은 종류 heartbeat 이면 in-place UPDATE.

    시간 범위 (start ~ end) 와 tick 수만 갱신 → DB row 1개로 collapse.
    점수 이벤트가 끼면 다음 heartbeat 부터 새로 시작 (이전 heartbeat row 는 그대로 보존).
    """
    now = dt.datetime.now(dt.timezone.utc)
    last = await session.scalar(
        select(BattleEvent).where(BattleEvent.battle_id == battle_id)
        .order_by(BattleEvent.id.desc()).limit(1)
    )
    targets_label = ",".join(target_apps) if target_apps else "(default)"

    is_collapsible_predecessor = (
        last is not None
        and last.event_type == "system"
        and last.target == "monitor"
        and (last.detail or {}).get("kind") == "heartbeat_range"
        and (last.points or 0) == 0
    )

    if is_collapsible_predecessor:
        d = dict(last.detail or {})
        ticks = int(d.get("ticks") or 1) + 1
        # start_ts 보존
        start_iso = d.get("start_ts") or (last.ts.isoformat() if last.ts else now.isoformat())
        try:
            start_dt = dt.datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
        except Exception:
            start_dt = last.ts or now
        d.update({
            "kind": "heartbeat_range",
            "start_ts": start_iso,
            "end_ts": now.isoformat(),
            "ticks": ticks,
            "monitor": monitor_mode,
            "target_apps": target_apps,
            "infras": infras_count,
            "last_tick_idx": tick_idx,
        })
        last.detail = d
        last.description = (
            f"auto-monitor heartbeat {_fmt_korean_time(start_dt)} ~ {_fmt_korean_time(now)} "
            f"({ticks}회, 변화 없음, monitor={monitor_mode})"
        )
        last.reasoning = (
            f"**자동 모니터 무변화 구간** ({_fmt_korean_time(start_dt)} ~ {_fmt_korean_time(now)})\n\n"
            f"이 시간 동안 자동 모니터가 **{ticks}회 점검**했고, 모든 probe 응답이 직전과 동일했습니다.\n\n"
            f"- 채점 모델: `{monitor_mode}`\n"
            f"- 점검 타겟: `{targets_label}`\n"
            f"- 인프라 수: {infras_count}\n\n"
            "_LLM 호출 없음 (변화가 없으면 token 소비 0). 새 점수 이벤트가 발생하면 다음 heartbeat 부터 새로 시작합니다._"
        )
        # ts 는 갱신하지 않음 (시간 정렬은 start_ts 유지) — UI 에선 description 의 범위가 우선
        await session.commit()
        return

    # 새 heartbeat row — bs.add_event 의 commit+refresh 사이클을 거치지 않고 바로 add+commit
    # (heartbeat 은 점수 0 이라 participant 점수 갱신/시간만료 체크 불필요)
    new_event = BattleEvent(
        battle_id=battle_id,
        actor_user_id=None,
        event_type="system",
        target="monitor",
        description=f"auto-monitor heartbeat {_fmt_korean_time(now)} (1회, monitor={monitor_mode})",
        points=0,
        detail={
            "kind": "heartbeat_range",
            "start_ts": now.isoformat(),
            "end_ts": now.isoformat(),
            "ticks": 1,
            "monitor": monitor_mode,
            "target_apps": target_apps,
            "infras": infras_count,
            "last_tick_idx": tick_idx,
        },
        reasoning=(
            f"**자동 모니터 시작** ({_fmt_korean_time(now)})\n\n"
            f"채점 모델 `{monitor_mode}` 로 타겟 `{targets_label}` 점검 시작."
        ),
    )
    session.add(new_event)
    await session.commit()


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
        # probe-hash + grader cache 정리
        for k in [k for k in list(_last_probe_hash.keys()) if k[0] == battle_id]:
            _last_probe_hash.pop(k, None)
        grader.clear_cache(battle_id)
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
    for k in [k for k in list(_last_probe_hash.keys()) if k[0] == battle_id]:
        _last_probe_hash.pop(k, None)
    grader.clear_cache(battle_id)


def is_running(battle_id: int) -> bool:
    t = _tasks.get(battle_id)
    return bool(t and not t.done())
