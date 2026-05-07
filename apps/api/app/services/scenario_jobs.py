"""시나리오 생성 background job tracker.

claude CLI 호출은 5~30초 걸릴 수 있으므로 비동기 task 로 띄우고 polling 으로 조회.
in-memory dict — 서버 재기동 시 초기화. Phase 6 에서 DB 로 이전 가능.
"""
from __future__ import annotations
import asyncio
import datetime as dt
import logging
import secrets
from typing import Any

from .scenario_gen import (
    GeneratedScenario, ScenarioGenerationError, generate_scenario,
)
from ..db import SessionLocal
from ..models import Scenario

log = logging.getLogger(__name__)


_jobs: dict[str, dict[str, Any]] = {}


def _new_job_id() -> str:
    return secrets.token_urlsafe(8)


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


async def _run_job(job_id: str, *, request: str, course_ref: str | None, weeks_spec: str | None,
                   created_by: int) -> None:
    job = _jobs[job_id]
    job["status"] = "running"
    job["started_at"] = _utcnow().isoformat()
    try:
        scenario, meta = await generate_scenario(
            request=request, course_ref=course_ref, weeks_spec=weeks_spec,
        )
        # DB 에 draft 로 저장
        async with SessionLocal() as s:
            row = Scenario(
                title=scenario.title,
                description=scenario.description,
                source="claude",
                course_ref=(course_ref or "claude-generated"),
                mission_red={
                    "missions": [m.model_dump() for m in scenario.red_missions],
                    "battle_type": scenario.battle_type_hint,
                },
                mission_blue={
                    "missions": [m.model_dump() for m in scenario.blue_missions],
                },
                scoring={
                    "red": {
                        "count": len(scenario.red_missions),
                        "total_points": sum(m.points for m in scenario.red_missions),
                    },
                    "blue": {
                        "count": len(scenario.blue_missions),
                        "total_points": sum(m.points for m in scenario.blue_missions),
                    },
                    "battle_type_hint": scenario.battle_type_hint,
                    "difficulty": scenario.difficulty,
                    "claude_meta": meta,
                },
                time_limit_sec=int(scenario.time_limit_sec),
                status="draft",
                created_by=created_by,
            )
            s.add(row)
            await s.commit()
            await s.refresh(row)
            job["scenario_id"] = row.id

        job["status"] = "completed"
        job["finished_at"] = _utcnow().isoformat()
        job["preview"] = {
            "title": scenario.title,
            "difficulty": scenario.difficulty,
            "time_limit_sec": scenario.time_limit_sec,
            "red_count": len(scenario.red_missions),
            "blue_count": len(scenario.blue_missions),
        }
        job["meta"] = meta
        log.info("scenario job %s ok scenario_id=%s", job_id, job.get("scenario_id"))
    except ScenarioGenerationError as e:
        job["status"] = "failed"
        job["finished_at"] = _utcnow().isoformat()
        job["error"] = str(e)
        log.warning("scenario job %s failed: %s", job_id, e)
    except Exception as e:
        job["status"] = "failed"
        job["finished_at"] = _utcnow().isoformat()
        job["error"] = f"{type(e).__name__}: {e}"
        log.exception("scenario job %s crashed", job_id)


def start_job(*, request: str, course_ref: str | None, weeks_spec: str | None,
              created_by: int) -> str:
    jid = _new_job_id()
    _jobs[jid] = {
        "id": jid,
        "status": "queued",
        "request": request,
        "course_ref": course_ref,
        "weeks_spec": weeks_spec,
        "created_by": created_by,
        "queued_at": _utcnow().isoformat(),
    }
    asyncio.create_task(_run_job(jid, request=request, course_ref=course_ref,
                                  weeks_spec=weeks_spec, created_by=created_by))
    return jid


def get_job(job_id: str) -> dict[str, Any] | None:
    return _jobs.get(job_id)


def list_jobs(limit: int = 50) -> list[dict[str, Any]]:
    rows = list(_jobs.values())
    rows.sort(key=lambda j: j.get("queued_at", ""), reverse=True)
    return rows[:limit]
