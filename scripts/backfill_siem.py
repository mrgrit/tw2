#!/usr/bin/env python3
"""중앙 SIEM 백필 — DB 의 코호트 활동(activity_events)을 tw2 OpenSearch 로 적재.

배경: seed/orchestrate 는 DB 에 직접 활동을 넣지만 중앙 SIEM(OpenSearch)엔 안 보낸다
(라이브 lab_monitor·채점 경로만 export 함). 데모/시연에서 Admin 의 '중앙 SIEM' 탭을 채우려면
이 스크립트로 기존 활동을 한 번 밀어넣는다. 멱등적이지 않음(재실행 시 중복 적재) → 필요하면
`--reset` 으로 인덱스 삭제 후 재적재.

사전조건: .env 에 OPENSEARCH_URL 설정 + tw2-opensearch 컨테이너 기동.
  docker run -d --name tw2-opensearch -p 127.0.0.1:9210:9200 \
    -e discovery.type=single-node -e DISABLE_SECURITY_PLUGIN=true \
    -e OPENSEARCH_JAVA_OPTS="-Xms512m -Xmx512m" opensearchproject/opensearch:2.11.1

사용: OPENSEARCH_URL=http://127.0.0.1:9210 .venv/bin/python scripts/backfill_siem.py [--cohort 3] [--reset]
"""
from __future__ import annotations
import os, sys, argparse, asyncio

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "apps", "api"))

# .env 의 OPENSEARCH_URL 을 자동 로드(명시 env 우선)
if not os.getenv("OPENSEARCH_URL"):
    envp = os.path.join(ROOT, ".env")
    if os.path.exists(envp):
        for line in open(envp):
            if line.startswith("OPENSEARCH_URL="):
                os.environ["OPENSEARCH_URL"] = line.split("=", 1)[1].strip()

from sqlalchemy import select  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import ActivityEvent, User, Battle, Cohort  # noqa: E402
from app.services import siem_export  # noqa: E402


async def chain_for(s, cohort_id: int) -> list:
    node = await s.get(Cohort, cohort_id)
    chain = []
    while node is not None:
        chain.append(node)
        node = await s.get(Cohort, node.parent_id) if node.parent_id else None
    chain.reverse()  # root→node
    return chain


async def main(cohort_id: int, reset: bool):
    if not siem_export.is_enabled():
        print("OPENSEARCH_URL 미설정 — 중앙 SIEM 비활성. .env 확인/컨테이너 기동 필요."); return
    async with SessionLocal() as s:
        chain = await chain_for(s, cohort_id)
        if not chain:
            print(f"코호트 {cohort_id} 없음."); return
        index = siem_export.physical_index_for(chain)
        print("chain:", " / ".join(f"{c.kind}:{c.name}" for c in chain), "→ index:", index)
        client = siem_export.default_client()

        if reset:
            import httpx
            async with httpx.AsyncClient(verify=False) as c:
                await c.delete(f"{os.environ['OPENSEARCH_URL'].rstrip('/')}/{index}")
            print("인덱스 삭제(reset).")

        # 서브트리 코호트 id 전체(섹션/팀 포함)의 활동
        sub_ids = {c.id for c in chain} | {cohort_id}
        battles = {b.id: b for b in (await s.scalars(
            select(Battle).where(Battle.cohort_id.in_(sub_ids)))).all()}
        users = {u.id: u.name for u in (await s.scalars(select(User))).all()}
        acts = (await s.scalars(select(ActivityEvent)
                .where(ActivityEvent.cohort_id.in_(sub_ids))
                .order_by(ActivityEvent.id))).all()
        events = [{
            "user_id": a.user_id, "user_name": users.get(a.user_id), "infra_id": None,
            "ts": a.ts.isoformat() if a.ts else None, "kind": a.kind,
            "scenario_step": a.scenario_step,
            "scenario_id": (battles.get(a.battle_id).scenario_id if battles.get(a.battle_id) else None),
            "payload": a.payload, "battle_id": a.battle_id,
        } for a in acts]
        res = await siem_export.export_events(client, events, chain)
        print(f"적재: {res['indexed']}건 → {res['index']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cohort", type=int, default=3, help="데모 섹션 코호트 id(기본 3)")
    ap.add_argument("--reset", action="store_true", help="인덱스 삭제 후 재적재(중복 방지)")
    a = ap.parse_args()
    asyncio.run(main(a.cohort, a.reset))
