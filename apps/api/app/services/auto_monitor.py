"""battle 활성화 시 background 자동 모니터 — 6v6 Assessor 연동.

목표: 학생이 6v6 에서 공격/방어를 진행하면 tubewar 가 그 효과를 **Assessor `/assess`**
(읽기 전용 채점 표면)로 관측해 BattleEvent 로 변환·점수 적용한다.

설계(불변):
- 15s 폴링, heartbeat 60s in-place collapse (변화 없으면 DB row 1개로 합침).
- monitor=bastion → LLM 0. monitor=claude → 결과가 모호할 때만 grader 가 analyzer(LLM) 호출.
- 미션별 check-spec 은 컴파일 후 mission.verify.checks 에 캐시 → 런타임 AI 0.
- blue 미션은 방어자 본인 infra(self), red 미션은 assess_target 에 따라 self/opponent infra
  에서 채점(cross-infra). 매칭 = 미션의 모든 check 가 passed.
- 한 battle 안에서 (side, order) 단위로 dedupe.
"""
from __future__ import annotations
import asyncio
import hashlib
import logging
import os
from typing import Any

import datetime as dt
from sqlalchemy import select

from ..db import SessionLocal
from ..models import Battle, BattleEvent, BattleParticipant, Infra, Scenario
from . import battle_service as bs, grader
from . import assessor_client, battlefield
from . import check_compiler as cc

log = logging.getLogger(__name__)

POLL_INTERVAL_SEC = 15.0
HEARTBEAT_EVERY_N_TICKS = 4  # 60s

_tasks: dict[int, asyncio.Task] = {}
_seen_hits: dict[int, set[tuple[str, int]]] = {}   # battle_id → set((side, order))
# 같은 battle 의 tick 직렬화 — 백그라운드 폴링 루프와 run_once(monitor-tick) 동시 실행 시
# _seen_hits 경쟁/중복·누락 채점 방지.
_locks: dict[int, asyncio.Lock] = {}


def _hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8", "ignore")).hexdigest()[:16]


def _auto_score_enabled() -> bool:
    """앰비언트 자동 채점(Assessor 상태만으로 점수 부여)은 **기본 OFF**.

    공격자가 만든 로그/알림 같은 앰비언트 상태로 방어자에게 점수가 들어가는 불공정을 막는다.
    채점은 학생 제출 + AI 시맨틱 검수(/battles/{id}/events)로만. 실험적으로 켜려면
    TUBEWAR_AUTO_SCORE=1.
    """
    return os.getenv("TUBEWAR_AUTO_SCORE", "0").lower() in ("1", "true", "yes")


def _missions_of(scenario: Scenario | None, side: str) -> list[dict]:
    if not scenario:
        return []
    container = (scenario.mission_red if side == "red" else scenario.mission_blue) or {}
    return container.get("missions") or []


async def _tick(battle_id: int, tick_idx: int) -> None:
    lock = _locks.setdefault(battle_id, asyncio.Lock())
    async with lock:
        await _tick_locked(battle_id, tick_idx)


async def _tick_locked(battle_id: int, tick_idx: int) -> None:
    async with SessionLocal() as s:
        battle = await s.get(Battle, battle_id)
        if not battle or battle.status != "active":
            raise StopAsyncIteration
        participants = (await s.scalars(
            select(BattleParticipant).where(BattleParticipant.battle_id == battle_id)
        )).all()

        # role → Infra 매핑 (solo/free 는 양쪽 role 에 동일 infra).
        role_infra: dict[str, Infra] = {}
        side_actor: dict[str, int] = {}
        infra_objs: dict[int, Infra] = {}
        for p in participants:
            inf = await s.get(Infra, p.infra_id) if p.infra_id else None
            if inf:
                infra_objs[inf.id] = inf
            if p.role in ("red", "blue"):
                if inf:
                    role_infra[p.role] = inf
                side_actor.setdefault(p.role, p.user_id)
            elif p.role in ("solo", "free"):
                if inf:
                    role_infra.setdefault("red", inf)
                    role_infra.setdefault("blue", inf)
                side_actor.setdefault("red", p.user_id)
                side_actor.setdefault("blue", p.user_id)

        scenario = await s.get(Scenario, battle.scenario_id) if battle.scenario_id else None
        target_apps = list(battle.target_apps or [])
        monitor_mode = battle.monitor or "bastion"
        infras_count = len(infra_objs)

    # heartbeat — 60s 마다. 변화 없으면 직전 heartbeat row 를 UPDATE.
    if tick_idx % HEARTBEAT_EVERY_N_TICKS == 0:
        async with SessionLocal() as s:
            try:
                await _emit_heartbeat(
                    s, battle_id=battle_id, monitor_mode=monitor_mode,
                    infras_count=infras_count, target_apps=target_apps, tick_idx=tick_idx,
                )
            except ValueError:
                raise StopAsyncIteration

    if not scenario or not role_infra:
        return

    # 앰비언트 자동 채점 기본 OFF — 채점은 학생 제출 + AI 검수로만(공정성).
    if not _auto_score_enabled():
        return

    seen = _seen_hits.setdefault(battle_id, set())

    # ── 채점 대상 infra 별로 check 를 모아 1회 /assess ──
    # infra.id → {"infra": Infra, "checks": [...], "missions": [(side, mission, actor, [check_ids])]}
    plan: dict[int, dict[str, Any]] = {}
    for side in ("blue", "red"):
        actor = side_actor.get(side)
        if actor is None:
            continue
        for m in _missions_of(scenario, side):
            order = int(m.get("order") or 0)
            points = int(m.get("points") or 0)
            if (side, order) in seen or points <= 0:
                continue
            assess_target = battlefield.normalize_assess_target(m.get("assess_target"))
            target_infra = battlefield.resolve_target_infra(side, assess_target, role_infra)
            if not target_infra:
                continue
            checks = cc.cache_checks_into_mission(m, side=side)
            if not checks:
                continue
            slot = plan.setdefault(target_infra.id, {"infra": target_infra, "checks": [], "missions": []})
            slot["checks"].extend(checks)
            slot["missions"].append((side, m, actor, [c["id"] for c in checks]))

    if not plan:
        return

    for infra_id, slot in plan.items():
        resp = await assessor_client.assess(slot["infra"], slot["checks"], battle_id=battle_id)
        if not resp.get("ok"):
            log.info("auto-monitor battle=%s assess failed infra=%s: %s",
                     battle_id, infra_id, resp.get("error"))
            continue
        by_id = assessor_client.results_by_id(resp)

        for (side, mission, actor, check_ids) in slot["missions"]:
            order = int(mission.get("order") or 0)
            if (side, order) in seen:
                continue
            mission_results = [by_id[cid] for cid in check_ids if cid in by_id]
            if not mission_results:
                continue
            verdict = await grader.judge_checks(
                monitor=monitor_mode, battle_id=battle_id, mission=mission,
                check_results=mission_results, side=side,
                scenario_title=scenario.title or "", course_ref=scenario.course_ref,
            )
            if not verdict.matched:
                continue

            points = int(mission.get("points") or 0)
            event_type = "detect" if side == "blue" else "exploit"
            async with SessionLocal() as s:
                try:
                    await bs.add_event(
                        s, battle_id=battle_id, actor_user_id=actor,
                        event_type=event_type, target=mission.get("target_vm") or "",
                        description=f"auto-monitor(Assessor) matched {side} #{order}",
                        points=points,
                        detail={
                            "source": "auto_monitor",
                            "assessor": True,
                            "side": side,
                            f"{side}_mission_order": order,
                            "scenario_id": scenario.id,
                            "monitor": monitor_mode,
                            "model": verdict.model,
                            "cost_usd": verdict.cost_usd,
                            "check_ids": check_ids,
                            "assessed_infra_id": infra_id,
                        },
                        reasoning=verdict.reasoning,
                    )
                    seen.add((side, order))   # 성공적으로 점수 부여한 뒤에만 dedupe 마킹
                    log.info(
                        "auto-monitor battle=%s %s#%s matched +%s mode=%s cost=%.4f",
                        battle_id, side, order, points, monitor_mode, verdict.cost_usd,
                    )
                except ValueError:
                    raise StopAsyncIteration


def _fmt_korean_time(d: dt.datetime) -> str:
    """오전/오후 H시 MM분 — heartbeat 표시용. 서버 로컬 TZ 와 무관하게 항상 KST(UTC+9)."""
    from .. import timeutil
    return timeutil.fmt_korean(d)


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
            f"이 시간 동안 자동 모니터가 **{ticks}회 점검**했고, Assessor 결과에 변화가 없었습니다.\n\n"
            f"- 채점 모델: `{monitor_mode}`\n"
            f"- 점검 타겟: `{targets_label}`\n"
            f"- 인프라 수: {infras_count}\n\n"
            "_결정론 check 는 LLM 호출 0. 새 점수 이벤트가 발생하면 다음 heartbeat 부터 새로 시작합니다._"
        )
        await session.commit()
        return

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
            f"채점 모델 `{monitor_mode}` 로 타겟 `{targets_label}` Assessor 점검 시작."
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
        _seen_hits.pop(battle_id, None)
        _locks.pop(battle_id, None)
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
    _seen_hits.pop(battle_id, None)
    _locks.pop(battle_id, None)
    grader.clear_cache(battle_id)


def is_running(battle_id: int) -> bool:
    t = _tasks.get(battle_id)
    return bool(t and not t.done())


# ── 테스트/수동 트리거용: 1회 채점 실행 (폴링 루프 없이) ──
async def run_once(battle_id: int, tick_idx: int = 1) -> None:
    """auto-monitor 의 1 tick 을 직접 실행. e2e/테스트에서 폴링 대기 없이 채점 확인용."""
    try:
        await _tick(battle_id, tick_idx)
    except StopAsyncIteration:
        return
