"""중앙 SIEM(OpenSearch + Dashboards) 적재 + 코호트 인덱스/뷰/RBAC 멱등 생성.

CC 의 프로그램적 채점/모니터링(→Postgres)과 **별개로**, 강사가 학생 활동을 **육안으로**
탐색하는 중앙 활동 lake. lab_monitor/auto_monitor 가 pull 한 `/activity`·`/assess`·battle
이벤트를 코호트 stamp 하여 중앙 OpenSearch 에 적재한다.

설계:
- **물리 인덱스 남발 금지**: 큰 단위(교과목/학기)만 물리 인덱스, 하위 코호트는 필드 태깅 +
  데이터뷰(saved-object)로 분리. 문서 필드: student/infra/ts/kind/cohort_path/scenario_step.
- **멱등·파라미터 템플릿**: 데이터뷰·대시보드·RBAC 롤/롤매핑을 현재→목표 상태로 reconcile.
  LLM free-form 금지(인덱스/롤 드리프트 방지).
- OpenSearch 미설정 시 **no-op**(disabled) — 플랫폼 로직은 막지 않는다.
- 클라이언트는 주입 가능(테스트는 in-memory Fake 사용). 실 클라이언트는 httpx.

이 모듈은 OpenSearch 클라이언트가 다음 async 메서드를 제공한다고 가정(duck typing):
  ensure_index(index) · bulk_index(index, docs)->int
  ensure_saved_object(otype, oid, attributes)->bool(created)
  ensure_role(name, index_pattern)->bool · ensure_role_mapping(role, users)->bool
"""
from __future__ import annotations
import logging
import os
import re

log = logging.getLogger(__name__)

INDEX_PREFIX = "tubewar-activity"
# 물리 인덱스를 만드는 '큰 단위' kind (이 중 가장 상위에 가까운 노드 기준)
_PHYSICAL_KINDS = ("course", "grade", "department")


def is_enabled() -> bool:
    return bool(os.getenv("OPENSEARCH_URL"))


def _slug(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9가-힣_-]+", "-", (text or "").strip().lower())
    return s.strip("-") or "x"


def cohort_path_str(chain: list) -> str:
    """root→node 체인 → 'kind:name/kind:name/...' 경로 문자열."""
    return "/".join(f"{c.kind}:{c.name}" for c in chain)


def physical_index_for(chain: list) -> str:
    """체인에서 '큰 단위'(course/grade/department) 노드를 골라 물리 인덱스명 산출.

    하위(section/team)는 별도 인덱스를 만들지 않고 이 인덱스에 필드 태깅으로 적재된다.
    """
    # 가장 구체적인 '큰 단위' 우선 (교과목 > 학년 > 학과).
    pick = None
    for kind in _PHYSICAL_KINDS:
        pick = next((c for c in chain if c.kind == kind), None)
        if pick is not None:
            break
    if pick is None:
        pick = chain[0] if chain else None
    if pick is None:
        return f"{INDEX_PREFIX}-identity"   # 신원-only(코호트 없음)
    ref = getattr(pick, "course_ref", None) or pick.name
    return f"{INDEX_PREFIX}-{_slug(str(ref))}"


def stamp(event: dict, chain: list) -> dict:
    """활동 이벤트를 코호트 문맥으로 stamp. 필드: student/infra/ts/kind/cohort_path/scenario_step."""
    return {
        "student": event.get("user_id"),
        "infra": event.get("infra_id"),
        "ts": event.get("ts"),
        "kind": event.get("kind"),
        "scenario_step": event.get("scenario_step"),
        "cohort_path": cohort_path_str(chain),
        "cohort_id": chain[-1].id if chain else None,
        "payload": event.get("payload"),
        "battle_id": event.get("battle_id"),
    }


async def export_events(client, events: list[dict], chain: list) -> dict:
    """이벤트 묶음을 코호트 stamp 후 물리 인덱스에 bulk 적재."""
    if client is None or not events:
        return {"indexed": 0, "index": None}
    index = physical_index_for(chain)
    await client.ensure_index(index)
    docs = [stamp(e, chain) for e in events]
    n = await client.bulk_index(index, docs)
    return {"indexed": n, "index": index}


async def ensure_cohort_objects(client, chain: list) -> dict:
    """코호트 데이터뷰 + 대시보드 + RBAC 롤/롤매핑 멱등 생성·reconcile.

    재실행 시 중복 없이 현재→목표. 데이터뷰는 물리 인덱스 + cohort_path 필터.
    """
    if client is None or not chain:
        return {"created": [], "disabled": client is None}
    node = chain[-1]
    index = physical_index_for(chain)
    path = cohort_path_str(chain)
    dv_id = f"dv-{node.id}"
    dash_id = f"dash-{node.id}"
    role = f"cohort-{node.id}"
    # 데이터뷰: 물리 인덱스를 대상으로, 이 코호트 경로로 필터링하는 saved-object.
    created: list[str] = []
    if await client.ensure_saved_object("index-pattern", dv_id, {
        "title": index, "cohort_path": path, "filter": {"cohort_id": node.id},
    }):
        created.append(f"index-pattern:{dv_id}")
    if await client.ensure_saved_object("dashboard", dash_id, {
        "title": f"코호트 {node.name} 활동", "data_view": dv_id, "cohort_id": node.id,
    }):
        created.append(f"dashboard:{dash_id}")
    # RBAC: 이 코호트 인덱스/뷰만 읽는 롤 + 강사 롤매핑.
    if await client.ensure_role(role, f"{index}*"):
        created.append(f"role:{role}")
    if await client.ensure_role_mapping(role, users=[]):
        created.append(f"role_mapping:{role}")
    return {"created": created, "index": index, "cohort_path": path, "role": role}


def dashboard_deeplink(chain: list) -> str | None:
    """tubewar UI 에서 강사가 자기 코호트 대시보드로 가는 딥링크 (RBAC 스코프)."""
    base = os.getenv("OPENSEARCH_DASHBOARDS_URL")
    if not base or not chain:
        return None
    return f"{base.rstrip('/')}/app/dashboards#/view/dash-{chain[-1].id}"


# ── 실 OpenSearch 클라이언트 (httpx) — 미설정/오류 시 호출부가 no-op 처리 ──
def default_client():
    """env 로 설정된 경우 실 클라이언트, 아니면 None(disabled)."""
    if not is_enabled():
        return None
    from ._opensearch_http import OpenSearchHttpClient   # lazy
    return OpenSearchHttpClient(
        os_url=os.environ["OPENSEARCH_URL"],
        dashboards_url=os.getenv("OPENSEARCH_DASHBOARDS_URL", ""),
        user=os.getenv("OPENSEARCH_USER", "admin"),
        password=os.getenv("OPENSEARCH_PASSWORD", "admin"),
    )
