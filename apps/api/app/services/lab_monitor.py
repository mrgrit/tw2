"""실습 모니터링 — 채점과 별개 트랙.

활성 lab(battle) 세션마다 각 학생 infra 의 Assessor `/activity` 를 N초 간격으로 pull 해
`ActivityEvent` 타임라인을 적재(Battle→Scenario step·Cohort 로 서버측 태깅)하고,
진도(step checks 통과율)와 병목 신호(결정론, LLM 0)를 산출한다.

병목 임계를 넘은 학생만 CC(feedback)로 넘긴다 — 대상자 거르기는 결정론, 작성만 CC.

설계:
- pull/적재/진도/병목 = LLM 0.
- 진도 step = 시나리오 미션(해당 side). step done = auto_monitor(Assessor) 가 그 order 를
  matched(점수 이벤트 detail.source==auto_monitor)로 표기한 것.
- 신원-only(cohort null) 도 동일 동작(cohort 태깅만 생략).
"""
from __future__ import annotations
import asyncio
import datetime as dt
import hashlib
import json
import logging
import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import SessionLocal
from ..models import (
    ActivityEvent, Battle, BattleEvent, BattleParticipant, Infra, ProgressSnapshot, Scenario,
)
from . import assessor_client

log = logging.getLogger(__name__)

POLL_INTERVAL_SEC = 20.0

# ── 병목 결정론 임계 ─────────────────────────────────
BOTTLENECK = {
    "repeated_failed_commands": 3,   # 같은 세션 내 실패 명령 누적
    "error_alerts": 5,               # alert/log 이벤트 누적
    "no_progress_sec": 300,          # 마지막 step 진전 이후 경과(활동은 있는데 진도 0)
}

_tasks: dict[int, asyncio.Task] = {}
# battle_id → user_id → 마지막으로 steps_done 가 증가한 시각
_last_progress_ts: dict[int, dict[int, dt.datetime]] = {}


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _aware(d: dt.datetime | None) -> dt.datetime | None:
    """sqlite naive datetime → UTC aware 정규화 (battle_service 관례)."""
    if d is None:
        return None
    return d.replace(tzinfo=dt.timezone.utc) if d.tzinfo is None else d


def _dedupe_key(kind: str, item: dict) -> str:
    blob = json.dumps(item, sort_keys=True, ensure_ascii=False, default=str)
    return f"{kind}:{hashlib.sha256(blob.encode('utf-8', 'ignore')).hexdigest()[:24]}"


def _missions_for_role(scenario: Scenario | None, role: str) -> list[dict]:
    if not scenario:
        return []
    red = (scenario.mission_red or {}).get("missions") or []
    blue = (scenario.mission_blue or {}).get("missions") or []
    if role == "red":
        return red
    if role == "blue":
        return blue
    return red + blue   # solo/free → 양쪽


def _solved_orders_by_side(events: list[BattleEvent]) -> dict[str, set[int]]:
    out: dict[str, set[int]] = {"red": set(), "blue": set()}
    for e in events:
        d = e.detail or {}
        if d.get("source") != "auto_monitor":
            continue
        for side in ("red", "blue"):
            o = d.get(f"{side}_mission_order")
            if o:
                out[side].add(int(o))
    return out


def _command_failed(payload: dict) -> bool:
    rc = payload.get("rc", payload.get("exit_code"))
    if isinstance(rc, int) and rc != 0:
        return True
    text = (str(payload.get("stdout", "")) + str(payload.get("stderr", "")) +
            str(payload.get("output", ""))).lower()
    return any(k in text for k in ("command not found", "permission denied", "error", "failed", "no such file"))


# ── /activity pull → ActivityEvent 적재 (dedupe) ─────
async def pull_activity_once(session: AsyncSession, battle_id: int, *, since_sec: int = 180) -> dict:
    battle = await session.get(Battle, battle_id)
    if not battle:
        return {"ingested": 0}
    participants = (await session.scalars(
        select(BattleParticipant).where(BattleParticipant.battle_id == battle_id)
    )).all()
    existing_keys = set((await session.scalars(
        select(ActivityEvent.dedupe_key).where(ActivityEvent.battle_id == battle_id)
    )).all())

    ingested = 0
    for p in participants:
        if not p.infra_id:
            continue
        infra = await session.get(Infra, p.infra_id)
        if not infra:
            continue
        resp = await assessor_client.activity(infra, since_sec=since_sec)
        if not resp.get("ok"):
            continue
        for kind, items in (("command", resp.get("commands") or []),
                            ("fim", resp.get("fim") or []),
                            ("alert", resp.get("alerts") or [])):
            for item in items:
                key = _dedupe_key(kind, item if isinstance(item, dict) else {"v": item})
                if key in existing_keys:
                    continue
                existing_keys.add(key)
                session.add(ActivityEvent(
                    battle_id=battle_id, cohort_id=battle.cohort_id, user_id=p.user_id,
                    infra_id=p.infra_id, kind=kind, dedupe_key=key,
                    payload=item if isinstance(item, dict) else {"value": item},
                ))
                ingested += 1
    if ingested:
        await session.commit()
    return {"ingested": ingested}


# ── 진도 + 병목 산출 (LLM 0) ─────────────────────────
def _bottleneck_flags(user_events: list[ActivityEvent], steps_done: int,
                      last_progress_ts: dt.datetime | None) -> dict:
    failed = sum(1 for e in user_events if e.kind == "command" and _command_failed(e.payload or {}))
    alerts = sum(1 for e in user_events if e.kind in ("alert", "log"))
    flags: dict = {}
    if failed >= BOTTLENECK["repeated_failed_commands"]:
        flags["repeated_failed_commands"] = failed
    if alerts >= BOTTLENECK["error_alerts"]:
        flags["error_alerts"] = alerts
    if user_events and last_progress_ts is not None:
        idle = (_now() - last_progress_ts).total_seconds()
        if steps_done == 0 and idle >= BOTTLENECK["no_progress_sec"]:
            flags["no_progress_sec"] = int(idle)
    return flags


async def snapshot_progress(session: AsyncSession, battle_id: int) -> list[dict]:
    """학생별 진도/병목 스냅샷 산출·저장(persist)."""
    return await compute_progress(session, battle_id, persist=True)


async def compute_progress(session: AsyncSession, battle_id: int, *, persist: bool = True) -> list[dict]:
    """학생별 진도/병목 산출. persist=True 면 ProgressSnapshot 저장(모니터),
    False 면 읽기 전용(대시보드 GET)."""
    battle = await session.get(Battle, battle_id)
    if not battle:
        return []
    scenario = await session.get(Scenario, battle.scenario_id) if battle.scenario_id else None
    participants = (await session.scalars(
        select(BattleParticipant).where(BattleParticipant.battle_id == battle_id)
    )).all()
    events = (await session.scalars(
        select(BattleEvent).where(BattleEvent.battle_id == battle_id)
    )).all()
    solved = _solved_orders_by_side(events)
    acts = (await session.scalars(
        select(ActivityEvent).where(ActivityEvent.battle_id == battle_id)
    )).all()
    acts_by_user: dict[int, list[ActivityEvent]] = {}
    for a in acts:
        if a.user_id is not None:
            acts_by_user.setdefault(a.user_id, []).append(a)

    prog_map = _last_progress_ts.setdefault(battle_id, {})
    out: list[dict] = []
    for p in participants:
        missions = _missions_for_role(scenario, p.role)
        orders = {int(m.get("order") or 0) for m in missions}
        if p.role in ("solo", "free"):
            done = (solved["red"] | solved["blue"]) & orders
        else:
            done = solved.get(p.role, set()) & orders
        steps_total = len(orders)
        steps_done = len(done)
        completion = round(100.0 * steps_done / steps_total, 1) if steps_total else 0.0

        # 진전 추적
        prev = prog_map.get(p.user_id)
        if steps_done > 0 and prev is None:
            prog_map[p.user_id] = _now()
        last_prog = _aware(prog_map.get(p.user_id) or battle.started_at)

        flags = _bottleneck_flags(acts_by_user.get(p.user_id, []), steps_done, last_prog)
        if persist:
            session.add(ProgressSnapshot(
                battle_id=battle_id, cohort_id=battle.cohort_id, user_id=p.user_id,
                completion=int(completion), steps_done=steps_done, steps_total=steps_total,
                bottleneck_flags=flags,
            ))
        out.append({
            "user_id": p.user_id, "completion": completion,
            "steps_done": steps_done, "steps_total": steps_total,
            "bottleneck_flags": flags, "stuck": bool(flags),
        })
    if persist:
        await session.commit()
    return out


async def run_lab_tick(battle_id: int, *, since_sec: int = 180, feedback_cb=None) -> dict:
    """1 tick: /activity pull → 진도/병목 스냅샷 → 막힌 학생만 feedback_cb 호출.

    feedback_cb(session, battle_id, user_id, progress) — stuck 학생에게만 호출(결정론 게이팅).
    """
    async with SessionLocal() as session:
        pulled = await pull_activity_once(session, battle_id, since_sec=since_sec)
        progress = await snapshot_progress(session, battle_id)
        stuck = [p for p in progress if p["stuck"]]
        if feedback_cb:
            for p in stuck:
                await feedback_cb(session, battle_id, p["user_id"], p)
    return {"ingested": pulled["ingested"], "students": len(progress), "stuck": len(stuck)}


async def _loop(battle_id: int, feedback_cb=None) -> None:
    log.info("lab-monitor START battle=%s", battle_id)
    try:
        while True:
            async with SessionLocal() as s:
                b = await s.get(Battle, battle_id)
                if not b or b.status != "active":
                    break
            try:
                await run_lab_tick(battle_id, feedback_cb=feedback_cb)
            except Exception:
                log.exception("lab-monitor tick error battle=%s", battle_id)
            await asyncio.sleep(POLL_INTERVAL_SEC)
    finally:
        _tasks.pop(battle_id, None)
        _last_progress_ts.pop(battle_id, None)
        log.info("lab-monitor STOP battle=%s", battle_id)


def start(battle_id: int, feedback_cb=None) -> None:
    if battle_id in _tasks and not _tasks[battle_id].done():
        return
    _tasks[battle_id] = asyncio.create_task(_loop(battle_id, feedback_cb))


def stop(battle_id: int) -> None:
    t = _tasks.pop(battle_id, None)
    if t and not t.done():
        t.cancel()
    _last_progress_ts.pop(battle_id, None)


def is_running(battle_id: int) -> bool:
    t = _tasks.get(battle_id)
    return bool(t and not t.done())


def autostart_enabled() -> bool:
    """battle 시작 시 백그라운드 lab 모니터 자동 기동 여부 (기본 OFF — 테스트 안정성)."""
    return os.getenv("TUBEWAR_LAB_MONITOR", "0").lower() in ("1", "true", "yes")
