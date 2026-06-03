"""중앙 SIEM 분석 — 필터(코호트/시나리오/학생/종류/기간) 빌드, 집계 shaping,
AI 로그분석 Q&A 의 provider 분기(CC/bastion). 실제 OpenSearch/LLM 없이 Fake 로 검증."""
from __future__ import annotations
import os
import pytest

os.environ.setdefault("TUBEWAR_FERNET_KEY", "ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg=")

from app.services import siem_export as se      # noqa: E402
from app.services import event_analyzer as ea   # noqa: E402


class C:
    def __init__(self, id, kind, name, course_ref=None):
        self.id, self.kind, self.name, self.course_ref = id, kind, name, course_ref


COURSE = [C(1, "department", "D"), C(2, "grade", "2"), C(3, "course", "웹해킹", course_ref="course3")]
SECTION = COURSE + [C(4, "section", "A")]


class RecFake:
    """search/aggregate 호출 body 를 기록하는 in-memory 클라이언트."""
    def __init__(self, docs=None, aggs=None, total=0):
        self.docs = docs or []
        self.aggs = aggs or {}
        self.total = total
        self.last = None

    async def search(self, index, body):
        self.last = (index, body)
        return list(self.docs)

    async def aggregate(self, index, body):
        self.last = (index, body)
        return {"aggs": self.aggs, "total": self.total}


def _musts(body):
    # 필터 없으면 match_all(=bool 없음) → 빈 리스트
    return body["query"].get("bool", {}).get("must", [])


@pytest.mark.asyncio
async def test_search_filters_subcohort():
    f = RecFake(docs=[{"ts": "2026-01-02"}, {"ts": "2026-01-03"}])
    r = await se.search_events(f, SECTION, kind="alert", student=3, scenario_id=1, time_from="now-7d")
    idx, body = f.last
    assert idx == "tubewar-activity-course3"          # 물리 인덱스는 course 기준
    musts = _musts(body)
    assert {"term": {"cohort_id": 4}} in musts          # section(하위) → cohort_id 필터
    assert {"term": {"scenario_id": 1}} in musts
    assert {"term": {"student": 3}} in musts
    assert {"term": {"kind.keyword": "alert"}} in musts
    assert any("range" in m for m in musts)             # 기간 필터
    assert r["docs"][0]["ts"] == "2026-01-03"           # 최근순 정렬


@pytest.mark.asyncio
async def test_search_physical_unit_has_no_cohort_term():
    f = RecFake()
    await se.search_events(f, COURSE)   # course = 물리 단위 → 인덱스 자체가 그 단위, cohort_id 필터 불필요
    _, body = f.last
    assert all(m.get("term", {}).get("cohort_id") is None for m in _musts(body))


@pytest.mark.asyncio
async def test_aggregate_shapes_buckets():
    aggs = {"by_kind": {"buckets": [{"key": "alert", "doc_count": 16}, {"key": "command", "doc_count": 3}]},
            "by_student": {"buckets": [{"key": 3, "doc_count": 16}]},
            "by_day": {"buckets": [{"key_as_string": "2026-06-03", "key": 1, "doc_count": 16}]}}
    f = RecFake(aggs=aggs, total=19)
    r = await se.aggregate(f, SECTION, time_from="now-30d")
    assert r["total"] == 19
    assert r["by_kind"] == [{"key": "alert", "count": 16}, {"key": "command", "count": 3}]
    assert r["by_student"] == [{"student": 3, "count": 16}]
    assert r["by_day"] == [{"date": "2026-06-03", "count": 16}]


@pytest.mark.asyncio
async def test_disabled_client_search_and_aggregate():
    r = await se.search_events(None, SECTION)
    assert r["enabled"] is False and r["docs"] == []
    r2 = await se.aggregate(None, SECTION)
    assert r2["enabled"] is False and r2["total"] == 0


@pytest.mark.asyncio
async def test_analyze_logs_provider_dispatch(monkeypatch):
    calls = {}

    async def fake_claude(system, user, model=None):
        calls["cc"] = model
        return "CC답변", 0.01

    async def fake_bastion(system, user, base_url, model, api_key):
        calls["bastion"] = (base_url, model)
        return "B답변", 0.0

    monkeypatch.setattr(ea, "_claude_text", fake_claude)
    monkeypatch.setattr(ea, "_bastion_text", fake_bastion)

    r = await ea.analyze_logs("q", {"stats": {}}, {"provider": "cc", "model": "claude-haiku-4-5"})
    assert r.reasoning == "CC답변" and r.model == "cc:claude-haiku-4-5"

    r2 = await ea.analyze_logs("q", {"stats": {}},
                               {"provider": "bastion", "model": "gpt-oss:120b", "base_url": "http://x:9100"})
    assert r2.reasoning == "B답변" and r2.model == "bastion:gpt-oss:120b"
    assert calls["bastion"] == ("http://x:9100", "gpt-oss:120b")


@pytest.mark.asyncio
async def test_analyze_logs_empty_response_marks_error(monkeypatch):
    async def none_claude(system, user, model=None):
        return None, 0.0
    monkeypatch.setattr(ea, "_claude_text", none_claude)
    r = await ea.analyze_logs("q", {}, {"provider": "cc", "model": "m"})
    assert r.model == "cc:error"
