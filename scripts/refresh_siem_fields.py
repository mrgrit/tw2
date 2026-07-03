#!/usr/bin/env python3
"""중앙 SIEM 데이터뷰 필드 새로고침 — 배틀/실습이 만든 dynamic 필드(payload.*)를 대시보드에 반영.

인덱스 매핑은 dynamic 이라 새 필드가 자동 생기지만 데이터뷰(index-pattern) saved-object 는
필드 스냅샷을 캐시한다 → 이 스크립트로 모든 코호트 데이터뷰의 필드를 현재 매핑 기준 재계산.
라이브 export 경로(ensure_cohort_objects)도 매 tick 갱신하지만, 배틀을 코호트 밖에서 돌렸거나
lab_monitor 가 꺼져 있던 구간을 보정하는 용도. cron/loop 로 주기 실행 가능.

usage: .venv/bin/python scripts/refresh_siem_fields.py [--cohort N]   (없으면 전 코호트)
"""
from __future__ import annotations
import os, sys, asyncio, argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "apps", "api"))
# .env 의 OPENSEARCH_* 로드(URL·DASHBOARDS_URL·USER·PASSWORD)
_envp = os.path.join(ROOT, ".env")
if os.path.exists(_envp):
    for _l in open(_envp):
        for _k in ("OPENSEARCH_URL", "OPENSEARCH_DASHBOARDS_URL", "OPENSEARCH_USER", "OPENSEARCH_PASSWORD"):
            if _l.startswith(_k + "=") and not os.getenv(_k):
                os.environ[_k] = _l.split("=", 1)[1].strip()

from sqlalchemy import select  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import Cohort  # noqa: E402
from app.services import siem_export, cohort_service  # noqa: E402


async def main(cohort_id: int | None):
    client = siem_export.default_client()
    if client is None:
        print("OPENSEARCH_URL 미설정 → siem_export 비활성. .env 확인."); return
    async with SessionLocal() as s:
        if cohort_id:
            ids = [cohort_id]
        else:
            ids = [c.id for c in (await s.execute(select(Cohort))).scalars().all()]
        n = 0
        for cid in ids:
            chain = await cohort_service.ancestor_chain(s, cid)
            if not chain:
                continue
            res = await siem_export.ensure_cohort_objects(client, chain)  # 필드 새로고침 포함
            refreshed = any(str(x).startswith("refresh-fields") for x in res.get("created", []))
            print(f"cohort {cid} ({chain[-1].name}) → index {res.get('index')} "
                  f"{'필드갱신✓' if refreshed else '(변화없음/스킵)'}")
            n += 1
        print(f"완료: {n} 코호트 데이터뷰 reconcile.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cohort", type=int, default=None)
    a = ap.parse_args()
    asyncio.run(main(a.cohort))
