"""CC 학생별 피드백 작성 — 활동 타임라인 + 진도 + 병목 + 채점 근거 → 개인화 피드백.

대상자 거르기는 결정론(lab_monitor 의 병목 신호), **작성만 CC(claude/haiku)**.
사실 날조 금지·정답 통째 금지(힌트/방향 수준)·한국어 markdown·근거 명시.

트리거 3종: 병목 임계(자동, lab_monitor → bottleneck_feedback_cb), lab/battle 종료, 강사 on-demand.
"""
from __future__ import annotations
import asyncio
import json
import logging
import os
import shutil

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import ActivityEvent, BattleEvent, ProgressSnapshot, StudentFeedback, User

log = logging.getLogger(__name__)

_CLAUDE_CMD = shutil.which("claude") or os.getenv("TUBEWAR_CLAUDE_BIN", "claude")
_CLAUDE_MODEL = os.getenv("TUBEWAR_FEEDBACK_MODEL", "claude-haiku-4-5")
_CLAUDE_TIMEOUT = float(os.getenv("TUBEWAR_FEEDBACK_TIMEOUT", "40"))

_SYSTEM = """\
You are a cyber-range teaching assistant writing PERSONALIZED feedback for one
student, in Korean markdown. You receive the student's activity timeline,
progress (step checks), deterministic bottleneck signals, and grading reasoning.

Write concise, actionable feedback:
- 무엇을 잘했는지 / 어디서 막혔는지 (근거 인용)
- 다음에 무엇을 점검·시도할지 (방향만 — 완전한 페이로드/비밀번호/정답을 통째로 적지 말 것)
Rules: 새로운 사실을 지어내지 말 것(주어진 데이터 안에서만). 정답 통째 금지(힌트 수준).
Output: Korean markdown only.
"""


async def _claude_feedback(payload: dict) -> tuple[str, str, float]:
    """claude CLI 로 피드백 작성. 실패 시 결정론 fallback(요약, 날조 없음)."""
    user = "## 피드백 입력 (JSON)\n```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```"
    try:
        proc = await asyncio.create_subprocess_exec(
            _CLAUDE_CMD, "-p", "--output-format", "json", "--model", _CLAUDE_MODEL,
            "--append-system-prompt", _SYSTEM, user,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        out, _err = await asyncio.wait_for(proc.communicate(), timeout=_CLAUDE_TIMEOUT)
        if proc.returncode != 0:
            raise RuntimeError("claude non-zero")
        wrap = json.loads(out.decode("utf-8", "replace"))
        text = (wrap.get("result") or "").strip()
        if not text:
            raise RuntimeError("empty")
        return text, _CLAUDE_MODEL, float(wrap.get("total_cost_usd") or 0.0)
    except Exception:
        return _fallback_summary(payload), "deterministic-fallback", 0.0


def _fallback_summary(payload: dict) -> str:
    """claude 미가용 시 — 입력 데이터만 요약(날조 없음, 정답 없음)."""
    prog = payload.get("progress") or {}
    flags = prog.get("bottleneck_flags") or {}
    lines = ["**자동 요약 (CC 미가용 — 결정론 요약)**", ""]
    lines.append(f"- 진도: {prog.get('steps_done', 0)}/{prog.get('steps_total', 0)} "
                 f"({prog.get('completion', 0)}%)")
    if flags:
        lines.append(f"- 병목 신호: {', '.join(flags.keys())}")
        lines.append("- 위 신호가 잡힌 단계를 다시 점검하세요 (명령 결과·로그 위주).")
    else:
        lines.append("- 특이 병목 신호 없음. 다음 단계 진행 권장.")
    return "\n".join(lines)


async def _gather_basis(session: AsyncSession, user_id: int, battle_id: int | None) -> dict:
    """피드백 근거 수집 — 진도 스냅샷 + 활동 event id + 채점 reasoning event id."""
    prog_q = select(ProgressSnapshot).where(ProgressSnapshot.user_id == user_id)
    if battle_id is not None:
        prog_q = prog_q.where(ProgressSnapshot.battle_id == battle_id)
    prog = await session.scalar(prog_q.order_by(ProgressSnapshot.id.desc()).limit(1))
    act_q = select(ActivityEvent.id, ActivityEvent.kind, ActivityEvent.payload).where(
        ActivityEvent.user_id == user_id)
    if battle_id is not None:
        act_q = act_q.where(ActivityEvent.battle_id == battle_id)
    acts = (await session.execute(act_q.order_by(ActivityEvent.id.desc()).limit(20))).all()

    grade_q = select(BattleEvent.id, BattleEvent.reasoning).where(
        BattleEvent.actor_user_id == user_id, BattleEvent.reasoning.is_not(None))
    if battle_id is not None:
        grade_q = grade_q.where(BattleEvent.battle_id == battle_id)
    grades = (await session.execute(grade_q.order_by(BattleEvent.id.desc()).limit(10))).all()

    return {
        "progress": {
            "steps_done": prog.steps_done if prog else 0,
            "steps_total": prog.steps_total if prog else 0,
            "completion": float(prog.completion) if prog else 0.0,
            "bottleneck_flags": prog.bottleneck_flags if prog else {},
        },
        "activity_event_ids": [a.id for a in acts],
        "activity_sample": [{"kind": a.kind, "payload": a.payload} for a in acts[:8]],
        "grading_reasoning_event_ids": [g.id for g in grades],
        "grading_reasoning_sample": [g.reasoning[:400] for g in grades[:3]],
    }


async def generate_feedback(
    session: AsyncSession, *, user_id: int, battle_id: int | None = None,
    cohort_id: int | None = None, scope: str = "lab", trigger: str = "manual",
    delivered_to: str = "both", note: str = "", created_by: int | None = None,
) -> StudentFeedback:
    """학생별 피드백 생성·저장. 작성만 CC, 나머지는 결정론."""
    u = await session.get(User, user_id)
    if not u:
        raise ValueError(f"user {user_id} not found")
    basis = await _gather_basis(session, user_id, battle_id)
    payload = {
        "student": {"name": u.name},
        "note_from_instructor": note,
        "progress": basis["progress"],
        "activity_sample": basis["activity_sample"],
        "grading_reasoning_sample": basis["grading_reasoning_sample"],
    }
    content_md, model, cost = await _claude_feedback(payload)

    fb = StudentFeedback(
        user_id=user_id, cohort_id=cohort_id, battle_id=battle_id,
        scope=scope, trigger=trigger, content_md=content_md,
        basis={
            "progress": basis["progress"],
            "activity_event_ids": basis["activity_event_ids"],
            "grading_reasoning_event_ids": basis["grading_reasoning_event_ids"],
        },
        model=model, cost_usd=int(round(cost * 1_000_000)),
        delivered_to=delivered_to, created_by=created_by,
    )
    session.add(fb)
    await session.commit()
    await session.refresh(fb)
    return fb


async def bottleneck_feedback_cb(session: AsyncSession, battle_id: int, user_id: int,
                                 progress: dict) -> None:
    """lab_monitor 의 stuck 학생 콜백 — 병목 트리거 피드백 작성.

    주의: 더 이상 주기 틱에서 자동 호출하지 않는다(폭주 방지). 피드백은 학생 제출 시
    `maybe_submission_feedback` 로만 트리거한다. (강사 on-demand 경로는 별도 유지.)
    """
    from ..models import Battle
    b = await session.get(Battle, battle_id)
    cohort_id = b.cohort_id if b else None
    await generate_feedback(
        session, user_id=user_id, battle_id=battle_id, cohort_id=cohort_id,
        scope="lab", trigger="bottleneck", delivered_to="both",
    )


# ── 제출 트리거 피드백 (틱 자동생성 대체) ──
# 끄려면 TUBEWAR_SUBMISSION_FEEDBACK=0. (user,battle) 당 쿨다운으로 폭주 재발 방지.
_SUBMISSION_FEEDBACK = os.getenv("TUBEWAR_SUBMISSION_FEEDBACK", "1") == "1"
_FB_COOLDOWN_SEC = float(os.getenv("TUBEWAR_FEEDBACK_COOLDOWN_SEC", "600"))   # 기본 10분
_fb_cooldown: dict[tuple[int, int], float] = {}


async def maybe_submission_feedback(
    session: AsyncSession, *, user_id: int, battle_id: int, cohort_id: int | None = None,
) -> "StudentFeedback | None":
    """학생 제출 시 호출 — struggling 학생에게만(호출부 게이팅) 피드백을 1건 작성한다.

    동일 (user, battle) 은 `_FB_COOLDOWN_SEC` 동안 1건으로 제한 → 자동 루프/연타 제출이
    피드백을 폭주시키지 못하게 한다. 비활성: TUBEWAR_SUBMISSION_FEEDBACK=0.
    """
    if not _SUBMISSION_FEEDBACK:
        return None
    import time as _time
    key = (int(user_id), int(battle_id))
    now = _time.monotonic()
    if now - _fb_cooldown.get(key, -1e9) < _FB_COOLDOWN_SEC:
        return None
    _fb_cooldown[key] = now            # 생성 전에 찍어 쿨다운 보장(연타 차단)
    return await generate_feedback(
        session, user_id=user_id, battle_id=battle_id, cohort_id=cohort_id,
        scope="lab", trigger="submission", delivered_to="both",
    )
