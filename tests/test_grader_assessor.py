"""grader.judge_checks — Assessor passed→점수, fail→미부여, 캐시, claude 모호 분기."""
from __future__ import annotations
import os
import pytest

os.environ.setdefault("TUBEWAR_FERNET_KEY", "ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg=")

from app.services import grader  # noqa: E402
from app.services import event_analyzer as ea  # noqa: E402

MISSION = {"order": 1, "instruction": "방어 미션", "points": 15, "target_vm": "web", "verify": {}}


@pytest.fixture(autouse=True)
def _clear_cache():
    grader._judge_cache.clear()
    yield
    grader._judge_cache.clear()


@pytest.mark.asyncio
async def test_passed_checks_matched_llm0():
    results = [{"id": "blue-1-1", "passed": True, "evidence": "200 OK in access.log"}]
    v = await grader.judge_checks(monitor="bastion", battle_id=1, mission=MISSION,
                                  check_results=results, side="blue")
    assert v.matched is True
    assert v.model == "assessor"
    assert v.cost_usd == 0.0
    assert "통과" in v.reasoning


@pytest.mark.asyncio
async def test_failed_check_not_matched():
    results = [{"id": "blue-1-1", "passed": False, "evidence": "no match"}]
    v = await grader.judge_checks(monitor="bastion", battle_id=1, mission=MISSION,
                                  check_results=results, side="blue")
    assert v.matched is False
    assert v.model == "assessor"


@pytest.mark.asyncio
async def test_partial_fail_not_matched():
    results = [
        {"id": "blue-1-1", "passed": True, "evidence": "ok"},
        {"id": "blue-1-2", "passed": False, "evidence": "missing"},
    ]
    v = await grader.judge_checks(monitor="bastion", battle_id=1, mission=MISSION,
                                  check_results=results, side="blue")
    assert v.matched is False


@pytest.mark.asyncio
async def test_cache_reuse():
    results = [{"id": "blue-1-1", "passed": True, "evidence": "ok"}]
    v1 = await grader.judge_checks(monitor="bastion", battle_id=7, mission=MISSION,
                                   check_results=results, side="blue")
    v2 = await grader.judge_checks(monitor="bastion", battle_id=7, mission=MISSION,
                                   check_results=results, side="blue")
    assert v1.cache_hit is False
    assert v2.cache_hit is True
    assert v2.reasoning == v1.reasoning


@pytest.mark.asyncio
async def test_claude_ambiguous_calls_analyzer(monkeypatch):
    called = {}

    async def fake_analyze(**kw):
        called["hit"] = True
        return ea.AnalysisResult(reasoning="LLM 보강 분석", model="claude-haiku-4-5", cost_usd=0.02)

    monkeypatch.setattr(ea, "analyze_event", fake_analyze)
    # passed=True 인데 evidence 없음 → 모호
    results = [{"id": "blue-1-1", "passed": True, "evidence": ""}]
    v = await grader.judge_checks(monitor="claude", battle_id=8, mission=MISSION,
                                  check_results=results, side="blue")
    assert called.get("hit") is True
    assert v.matched is True
    assert v.model == "claude-haiku-4-5"
    assert v.cost_usd == 0.02


@pytest.mark.asyncio
async def test_claude_clear_evidence_is_llm0(monkeypatch):
    called = {}

    async def fake_analyze(**kw):
        called["hit"] = True
        return ea.AnalysisResult(reasoning="x", model="claude", cost_usd=1.0)

    monkeypatch.setattr(ea, "analyze_event", fake_analyze)
    # 결정론 check (evidence 명확) → claude 라도 LLM 0
    results = [{"id": "blue-1-1", "passed": True, "evidence": "clear evidence"}]
    v = await grader.judge_checks(monitor="claude", battle_id=9, mission=MISSION,
                                  check_results=results, side="blue")
    assert "hit" not in called
    assert v.model == "assessor"
    assert v.cost_usd == 0.0


@pytest.mark.asyncio
async def test_bastion_ambiguous_still_llm0(monkeypatch):
    called = {}

    async def fake_analyze(**kw):
        called["hit"] = True
        return ea.AnalysisResult(reasoning="x", model="claude", cost_usd=1.0)

    monkeypatch.setattr(ea, "analyze_event", fake_analyze)
    results = [{"id": "blue-1-1", "passed": True, "evidence": ""}]
    v = await grader.judge_checks(monitor="bastion", battle_id=10, mission=MISSION,
                                  check_results=results, side="blue")
    assert "hit" not in called
    assert v.model == "assessor"
