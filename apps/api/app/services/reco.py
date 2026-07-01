"""AI 추천 직무 — 학생의 채점 통과 제출에서 강점 태그를 추출해 직무를 매칭.

결정론(날조 없음): 제출의 mission_side/event_type + 시나리오 category 를 태그로 환산하고,
직무 카탈로그와 태그 겹침으로 점수화·랭킹한다. 근거(why)는 실제 신호에서 문구화한다.
"""
from __future__ import annotations
from collections import Counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Scenario, StudentSubmission

JOB_CATALOG = [
    {"id": "web-pentest", "title": "웹 모의해킹 전문가",
     "tags": {"web", "exploit", "offensive", "pentest"},
     "desc": "웹 애플리케이션 취약점을 발굴·검증하는 공격 관점 전문가."},
    {"id": "redteam", "title": "레드팀 오퍼레이터",
     "tags": {"offensive", "red", "pentest", "lateral"},
     "desc": "실제 공격자 관점으로 조직 방어를 시험하는 공격 시뮬레이션 전문가."},
    {"id": "soc", "title": "SOC 분석가",
     "tags": {"soc", "detection", "blue", "alert", "log"},
     "desc": "보안관제센터에서 로그·알림을 분석해 위협을 탐지·대응."},
    {"id": "dfir", "title": "침해대응(DFIR) 담당자",
     "tags": {"ir", "detection", "blue", "forensics"},
     "desc": "사고 발생 시 증거를 수집·분석하고 복구를 주도."},
    {"id": "vuln", "title": "취약점 진단원",
     "tags": {"web", "recon", "pentest", "scanning"},
     "desc": "시스템·웹의 취약점을 체계적으로 진단·보고."},
    {"id": "aisec", "title": "AI 보안 엔지니어",
     "tags": {"ai", "llm", "prompt-injection", "offensive"},
     "desc": "LLM/AI 서비스의 프롬프트 인젝션 등 신규 위협을 평가·방어."},
]

# 시나리오 category → 태그 (느슨 매칭; 미분류는 무시)
CATEGORY_TAGS: dict[str, set[str]] = {
    "secuops-easy": {"soc", "detection", "blue"},
    "secuops": {"soc", "detection", "blue"},
    "soc": {"soc", "detection", "blue", "log", "alert"},
    "soc-adv": {"soc", "detection", "blue", "forensics", "ir"},
    "attack": {"offensive", "red", "pentest", "web"},
    "attack-adv": {"offensive", "red", "pentest", "lateral"},
    "web": {"web", "exploit"},
    "ai-service-pentest": {"ai", "llm", "prompt-injection", "offensive"},
    "ai-security": {"ai", "llm", "detection"},
    "iot-security": {"recon", "scanning"},
}

TAG_PHRASE = {
    "offensive": "공격 관점 수행", "red": "RED 미션 통과", "pentest": "침투 절차 수행",
    "web": "웹 취약점 공략", "exploit": "익스플로잇 실행", "lateral": "측면이동 시도",
    "blue": "BLUE 방어 수행", "detection": "탐지·분석", "soc": "로그/알림 분석",
    "ir": "대응 절차 수행", "forensics": "증거 수집", "recon": "정찰 수행",
    "scanning": "취약점 스캐닝", "ai": "AI 서비스 평가", "llm": "LLM 취약점 공략",
    "prompt-injection": "프롬프트 인젝션",
}


async def _student_tags(session: AsyncSession, user_id: int) -> Counter:
    """채점 통과(pass) 제출에서 강점 태그를 집계."""
    subs = (await session.scalars(
        select(StudentSubmission).where(
            StudentSubmission.user_id == user_id,
            StudentSubmission.grade_status == "graded",
        )
    )).all()
    # 시나리오 category 한 번에 조회
    sids = {s.scenario_id for s in subs if s.scenario_id}
    cats: dict[int, str | None] = {}
    if sids:
        cats = dict((await session.execute(
            select(Scenario.id, Scenario.category).where(Scenario.id.in_(sids))
        )).all())
    tags: Counter = Counter()
    for s in subs:
        if (s.verdict or "").lower() not in ("pass", "partial"):
            continue
        w = 2 if (s.verdict or "").lower() == "pass" else 1
        if s.mission_side == "red":
            for t in ("offensive", "red", "pentest"):
                tags[t] += w
        elif s.mission_side == "blue":
            for t in ("blue", "detection", "soc"):
                tags[t] += w
        if s.event_type == "exploit":
            tags["web"] += w; tags["exploit"] += w
        elif s.event_type == "defend":
            tags["detection"] += w; tags["ir"] += w
        for t in CATEGORY_TAGS.get(cats.get(s.scenario_id) or "", set()):
            tags[t] += 1
    return tags


async def recommend_jobs(session: AsyncSession, user_id: int, top: int = 3) -> list[dict]:
    """상위 직무 추천 — [{id,title,desc,match,why,score}] (근거 있는 것만)."""
    tags = await _student_tags(session, user_id)
    if not tags:
        return []
    scored = [(job, sum(tags[t] for t in job["tags"])) for job in JOB_CATALOG]
    scored = [x for x in scored if x[1] > 0]
    scored.sort(key=lambda x: x[1], reverse=True)
    if not scored:
        return []
    top_score = scored[0][1]
    out: list[dict] = []
    for job, score in scored[:top]:
        match = int(round(60 + 39 * score / top_score))          # 60~99 로 정규화
        why = [TAG_PHRASE[t] for t in job["tags"] if tags.get(t)]  # 이 직무와 겹치는 강점
        why = sorted(set(why), key=lambda p: -max(
            (tags[t] for t, ph in TAG_PHRASE.items() if ph == p), default=0))[:3]
        out.append({"id": job["id"], "title": job["title"], "desc": job["desc"],
                    "match": match, "why": why, "score": score})
    return out
