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
import json
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


# 이벤트 그룹 분류 — 유사건을 고정 group_no 로 묶고, 분석 중요 필드를 top-level 로 분리.
# 건별 개별 필드 폭증을 막으면서(payload 는 원본 유지) 대시보드에서 group_no/phase/evt_* 로 딱딱 필터.
# group_no 대역: 10 정찰 · 20 익스플로잇(웹) · 30 접근/인증 · 40 실행 · 50 무결성 · 90 기타.
def classify(kind: str, payload) -> dict:
    p = payload if isinstance(payload, dict) else {}
    src = str(p.get("src") or "").lower()
    text = str(p.get("desc") or p.get("rule") or p.get("value") or "").lower()
    # 분석 중요 필드 분리(top-level)
    out = {
        "evt_src": p.get("src"),
        "evt_signature": p.get("rule") or (p.get("desc") if kind == "alert" else None),
        "evt_rule_id": p.get("rule_id"),
        "evt_cmd": p.get("cmd"),
        "evt_rc": p.get("rc"),
        "evt_path": p.get("path") or p.get("file"),
    }
    if kind == "fim":
        g, no, ph, sev = "파일무결성(FIM)", 50, "persistence", "medium"
    elif kind == "command":
        rc = p.get("rc")
        if rc not in (0, None, "0"):
            g, no, ph, sev = "명령실패", 41, "exploit", "low"
        else:
            g, no, ph, sev = "명령실행", 40, "exploit", "medium"
    else:  # alert
        if "suricata" in src or any(w in text for w in ("scan", "nmap", "syn", "portscan")):
            g, no, ph, sev = "IDS-정찰스캔", 10, "recon", "medium"
        elif any(w in src for w in ("modsec", "waf", "apache")) or "modsec" in text:
            if any(w in text for w in ("union", "sqli", "942", "' or", "or 1=1")):
                g, no, ph, sev = "WAF-SQLi", 20, "exploit", "high"
            elif any(w in text for w in ("xss", "<script", "941", "onerror")):
                g, no, ph, sev = "WAF-XSS", 21, "exploit", "high"
            elif any(w in text for w in ("sqlmap", "nikto", "scanner", "913", "auto-red")):
                g, no, ph, sev = "WAF-스캐너탐지", 22, "recon", "medium"
            else:
                g, no, ph, sev = "WAF-기타차단", 29, "exploit", "medium"
        elif "wazuh" in src:
            if any(w in text for w in ("sshd", "session", "authentication", "login", "pam_unix")):
                g, no, ph, sev = "인증-세션", 30, "access", "low"
            else:
                g, no, ph, sev = "SIEM-경보", 39, "detection", "low"
        else:
            g, no, ph, sev = "기타경보", 90, "other", "info"
    out.update({"group": g, "group_no": no, "phase": ph, "severity": sev})
    return {k: v for k, v in out.items() if v not in (None, "")}


def stamp(event: dict, chain: list) -> dict:
    """활동 이벤트를 코호트 문맥으로 stamp + 이벤트 분류(그룹/중요필드 분리).

    상위 스키마: student/infra/ts/kind/cohort_path/scenario_step + 분류(group/group_no/phase/
    severity/evt_*). payload 원본도 보존. dynamic 매핑이라 신규 필드는 자동 생성."""
    doc = {
        "student": event.get("user_id"),
        "student_name": event.get("user_name"),
        "infra": event.get("infra_id"),
        "ts": event.get("ts"),
        "kind": event.get("kind"),
        "scenario_step": event.get("scenario_step"),
        "scenario_id": event.get("scenario_id"),
        "cohort_path": cohort_path_str(chain),
        "cohort_id": chain[-1].id if chain else None,
        "payload": event.get("payload"),
        "battle_id": event.get("battle_id"),
    }
    doc.update(classify(event.get("kind"), event.get("payload")))
    return doc


async def export_events(client, events: list[dict], chain: list) -> dict:
    """이벤트 묶음을 코호트 stamp 후 물리 인덱스에 bulk 적재."""
    if client is None or not events:
        return {"indexed": 0, "index": None}
    index = physical_index_for(chain)
    await client.ensure_index(index)
    docs = [stamp(e, chain) for e in events]
    n = await client.bulk_index(index, docs)
    return {"indexed": n, "index": index}


def _scope_query(node) -> str:
    """이 코호트 노드의 KQL 스코프. 물리 단위(course/grade/department)는 인덱스 자체가
    그 단위라 필터 불필요(=전체) → 빈 문자열. 하위(section/team)는 cohort_id 로 좁힌다."""
    return "" if node.kind in _PHYSICAL_KINDS else f"cohort_id: {node.id}"


async def ensure_cohort_objects(client, chain: list) -> dict:
    """코호트 데이터뷰 + 저장검색 + 대시보드 + RBAC 롤/롤매핑 멱등 생성·reconcile.

    실제 OpenSearch Dashboards saved-object 로 만들어 tubewar UI 안 iframe 으로 바로 렌더된다:
      index-pattern(dv-N, 시간필드 ts) → search(se-N, 코호트 스코프 + 컬럼) → dashboard(dash-N, 표 패널)
    재실행 시 중복 없이 현재→목표(존재하면 skip).
    """
    if client is None or not chain:
        return {"created": [], "disabled": client is None}
    node = chain[-1]
    index = physical_index_for(chain)
    path = cohort_path_str(chain)
    dv_id, se_id, dash_id = f"dv-{node.id}", f"se-{node.id}", f"dash-{node.id}"
    role = f"cohort-{node.id}"
    created: list[str] = []

    # 1) 데이터뷰(index-pattern): 물리 인덱스 + 시간 필드 ts.
    if await client.ensure_saved_object("index-pattern", dv_id,
                                        {"title": index, "timeFieldName": "ts"}):
        created.append(f"index-pattern:{dv_id}")
    # 1b) 필드 새로고침 — dynamic 매핑(배틀/실습별 payload.* 신규 필드)을 데이터뷰에 반영.
    #     데이터뷰가 존재해도(멱등 skip) 필드는 매 reconcile 갱신해야 대시보드에 새 필드가 뜬다.
    if hasattr(client, "refresh_index_pattern"):
        if await client.refresh_index_pattern(dv_id, index):
            created.append(f"refresh-fields:{dv_id}")

    # 2) 저장검색(search): 이 코호트로 스코프 + 활동 표 컬럼. dv 를 reference 로 연결.
    ssj = {"indexRefName": "kibanaSavedObjectMeta.searchSourceJSON.index",
           "query": {"query": _scope_query(node), "language": "kuery"}, "filter": []}
    if await client.ensure_saved_object(
        "search", se_id,
        {"title": f"{node.name} 활동(검색)",
         "columns": ["student_name", "kind", "cohort_path", "payload"],
         "sort": [["ts", "desc"]],
         "kibanaSavedObjectMeta": {"searchSourceJSON": json.dumps(ssj)}},
        references=[{"name": "kibanaSavedObjectMeta.searchSourceJSON.index",
                     "type": "index-pattern", "id": dv_id}],
    ):
        created.append(f"search:{se_id}")

    # 3) 대시보드(dashboard): 저장검색을 표 패널로 임베드 (search 를 reference 로 연결).
    panels = [{"version": "2.18.0",
               "gridData": {"x": 0, "y": 0, "w": 48, "h": 18, "i": "1"},
               "panelIndex": "1", "embeddableConfig": {}, "panelRefName": "panel_1"}]
    if await client.ensure_saved_object(
        "dashboard", dash_id,
        {"title": f"코호트 {node.name} 활동(SIEM)",
         "panelsJSON": json.dumps(panels),
         "optionsJSON": json.dumps({"useMargins": True, "hidePanelTitles": False}),
         "timeRestore": True, "timeFrom": "now-30d", "timeTo": "now",
         "kibanaSavedObjectMeta": {
             "searchSourceJSON": json.dumps({"query": {"query": "", "language": "kuery"},
                                             "filter": []})}},
        references=[{"name": "panel_1", "type": "search", "id": se_id}],
    ):
        created.append(f"dashboard:{dash_id}")

    # 4) RBAC: 이 코호트 인덱스/뷰만 읽는 롤 + 강사 롤매핑.
    if await client.ensure_role(role, f"{index}*"):
        created.append(f"role:{role}")
    if await client.ensure_role_mapping(role, users=[]):
        created.append(f"role_mapping:{role}")
    return {"created": created, "index": index, "cohort_path": path, "role": role}


def _scope_kind(node) -> str | None:
    return None if node.kind in _PHYSICAL_KINDS else "sub"


def _build_filters(chain: list | None, *, scenario_id: int | None = None,
                   student: int | None = None, kind: str | None = None,
                   time_from: str | None = None, time_to: str | None = None,
                   q: str | None = None) -> list[dict]:
    """공통 bool.must 필터 빌더 — 코호트/시나리오/학생/종류/기간/검색어."""
    must: list[dict] = []
    if chain:
        node = chain[-1]
        # 물리 단위(course/grade/department) 는 인덱스 자체가 그 단위 → cohort_id 추가필터 불필요.
        if _scope_kind(node) == "sub":
            must.append({"term": {"cohort_id": node.id}})
    if scenario_id is not None:
        must.append({"term": {"scenario_id": scenario_id}})
    if student is not None:
        must.append({"term": {"student": student}})
    if kind:
        must.append({"term": {"kind.keyword": kind}})
    if time_from or time_to:
        rng: dict = {}
        if time_from:
            rng["gte"] = time_from
        if time_to:
            rng["lte"] = time_to
        must.append({"range": {"ts": rng}})
    if q:
        must.append({"query_string": {"query": q}})
    return must


async def search_events(client, chain: list | None = None, *, limit: int = 100,
                        q: str | None = None, scenario_id: int | None = None,
                        student: int | None = None, kind: str | None = None,
                        time_from: str | None = None, time_to: str | None = None) -> dict:
    """중앙 SIEM(OpenSearch)에서 활동 문서 조회 — tubewar UI 에 임베드해 강사가 보게 한다.

    chain 주면 해당 코호트(서브트리) 로 필터. 시나리오/학생/종류/기간/검색어로 좁힐 수 있다.
    """
    if client is None:
        return {"enabled": False, "docs": [], "index": None}
    index = physical_index_for(chain) if chain else f"{INDEX_PREFIX}-*"
    must = _build_filters(chain, scenario_id=scenario_id, student=student, kind=kind,
                          time_from=time_from, time_to=time_to, q=q)
    body = {"size": max(1, min(limit, 500)),
            "sort": [{"ts": {"order": "desc", "unmapped_type": "date"}}],
            "query": {"bool": {"must": must}} if must else {"match_all": {}}}
    docs = await client.search(index, body)
    docs.sort(key=lambda d: str(d.get("ts") or ""), reverse=True)
    return {"enabled": True, "index": index, "docs": docs}


async def aggregate(client, chain: list | None = None, *, scenario_id: int | None = None,
                    student: int | None = None, kind: str | None = None,
                    time_from: str | None = None, time_to: str | None = None,
                    q: str | None = None) -> dict:
    """활동 통계(집계) — 총건수 / 종류별 / 학생별 / 일자별(시계열). 로그 테이블 위 요약용."""
    if client is None:
        return {"enabled": False, "total": 0, "by_kind": [], "by_student": [], "by_day": []}
    index = physical_index_for(chain) if chain else f"{INDEX_PREFIX}-*"
    must = _build_filters(chain, scenario_id=scenario_id, student=student, kind=kind,
                          time_from=time_from, time_to=time_to, q=q)
    body = {
        "size": 0,
        "query": {"bool": {"must": must}} if must else {"match_all": {}},
        "aggs": {
            "by_kind": {"terms": {"field": "kind.keyword", "size": 20}},
            "by_student": {"terms": {"field": "student", "size": 100}},
            "by_scenario": {"terms": {"field": "scenario_id", "size": 40}},
            "by_day": {"date_histogram": {"field": "ts", "calendar_interval": "day",
                                          "min_doc_count": 1}},
            # 학생 × 종류 피벗 매트릭스 (학생별로 종류 분포 sub-agg).
            "pivot": {"terms": {"field": "student", "size": 60},
                      "aggs": {"kinds": {"terms": {"field": "kind.keyword", "size": 12}}}},
        },
    }
    res = await client.aggregate(index, body)
    aggs = res.get("aggs") or {}
    bk = [{"key": b["key"], "count": b["doc_count"]}
          for b in (aggs.get("by_kind", {}).get("buckets") or [])]
    bs = [{"student": b["key"], "count": b["doc_count"]}
          for b in (aggs.get("by_student", {}).get("buckets") or [])]
    bsc = [{"scenario_id": b["key"], "count": b["doc_count"]}
           for b in (aggs.get("by_scenario", {}).get("buckets") or [])]
    bd = [{"date": b.get("key_as_string") or b.get("key"), "count": b["doc_count"]}
          for b in (aggs.get("by_day", {}).get("buckets") or [])]
    pivot = [{"student": b["key"], "total": b["doc_count"],
              "kinds": {k["key"]: k["doc_count"] for k in (b.get("kinds", {}).get("buckets") or [])}}
             for b in (aggs.get("pivot", {}).get("buckets") or [])]
    return {"enabled": True, "index": index, "total": int(res.get("total") or 0),
            "by_kind": bk, "by_student": bs, "by_scenario": bsc, "by_day": bd, "pivot": pivot}


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
    # 저장객체(dataview) ops 는 내부 URL 우선 — 공개 터널(trycloudflare)은 saved-object API 에
    # 400 을 주므로 로컬 OSD 를 쓴다. 딥링크(브라우저용)는 dashboard_deeplink 가 공개 URL 사용.
    ops_dash = (os.getenv("OPENSEARCH_DASHBOARDS_INTERNAL_URL")
                or os.getenv("OPENSEARCH_DASHBOARDS_URL", ""))
    return OpenSearchHttpClient(
        os_url=os.environ["OPENSEARCH_URL"],
        dashboards_url=ops_dash,
        user=os.getenv("OPENSEARCH_USER", "admin"),
        password=os.getenv("OPENSEARCH_PASSWORD", "admin"),
    )
