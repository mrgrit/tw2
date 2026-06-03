"""contents/battle-scenarios/*.yaml 을 DB 의 Scenario 로 import.

각 YAML 의 표준 키:
  id, title, description, difficulty, time_limit, battle_type, red_missions, blue_missions

DB 매핑:
  - id (string)         → Scenario.course_ref (slug 보존)
  - title               → Scenario.title
  - description         → Scenario.description
  - red_missions / blue_missions → Scenario.mission_red / mission_blue
  - 점수 합계 + 미션 개수 → Scenario.scoring (메타)
  - time_limit          → Scenario.time_limit_sec (없으면 1800)
  - battle_type         → mission 메타로 보존 (활용은 Phase 3+)

idempotent: title 매칭 기준으로 이미 존재하면 skip (단, 평소 dev 로 충분).
"""
from __future__ import annotations
import logging
from pathlib import Path
from typing import Any
import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Scenario

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[4]
_SCENARIO_DIR = _REPO_ROOT / "contents" / "battle-scenarios"


def _summary(missions: list[dict[str, Any]] | None) -> dict[str, Any]:
    missions = missions or []
    total_points = sum(int(m.get("points") or 0) for m in missions)
    return {
        "count": len(missions),
        "total_points": total_points,
        "orders": [m.get("order") for m in missions],
    }


def _normalize(raw: dict[str, Any], slug: str) -> dict[str, Any]:
    red = raw.get("red_missions") or []
    blue = raw.get("blue_missions") or []
    scoring = {
        "red": _summary(red),
        "blue": _summary(blue),
        "battle_type_hint": raw.get("battle_type") or "1v1",
        "difficulty": raw.get("difficulty") or "medium",
    }
    # 카테고리: YAML 의 category(권장) → 없으면 course → 없으면 미분류(None).
    category = raw.get("category") or raw.get("course")
    return {
        "title": str(raw.get("title") or slug),
        "description": str(raw.get("description") or ""),
        "category": str(category) if category else None,
        "course_ref": str(raw.get("id") or slug),
        "mission_red": {"missions": red, "battle_type": raw.get("battle_type") or "1v1"},
        "mission_blue": {"missions": blue},
        "scoring": scoring,
        "time_limit_sec": int(raw.get("time_limit") or 1800),
        "status": "validated",
        "source": "admin",
    }


async def import_scenarios(session: AsyncSession, scenario_dir: Path | None = None) -> int:
    """scenarios/ 의 YAML 들을 idempotent 하게 import. 반환=새로 들어간 개수."""
    d = scenario_dir or _SCENARIO_DIR
    if not d.exists():
        log.warning("scenario dir not found: %s", d)
        return 0

    # 파일(YAML)이 시나리오 '내용' 의 source of truth — 재로딩 시 내용 필드는 갱신(upsert)하되
    # 운영 설정(grader_profile_id)·아카이브 상태는 보존한다. UI 는 미션 내용을 편집하지 않으므로 충돌 없음.
    _CONTENT_FIELDS = ("title", "description", "category", "mission_red",
                       "mission_blue", "scoring", "time_limit_sec")
    inserted = 0
    updated = 0
    for path in sorted(d.glob("*.yaml")):
        slug = path.stem
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception as e:
            log.error("failed to parse %s: %s", path, e)
            continue
        if not isinstance(raw, dict):
            continue

        normalized = _normalize(raw, slug)
        existing = await session.scalar(
            select(Scenario).where(Scenario.course_ref == normalized["course_ref"])
        )
        if existing:
            changed = False
            for f in _CONTENT_FIELDS:
                if getattr(existing, f) != normalized[f]:
                    setattr(existing, f, normalized[f])
                    changed = True
            # archived 가 아니면 validated 로 유지(draft→validated 승격 허용), archived 는 보존.
            if existing.status not in ("validated", "archived"):
                existing.status = "validated"
                changed = True
            if changed:
                updated += 1
            continue

        session.add(Scenario(**normalized))
        inserted += 1

    if inserted or updated:
        await session.commit()
        log.info("scenarios: %d new, %d updated from %s", inserted, updated, d)
    return inserted
