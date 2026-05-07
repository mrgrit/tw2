"""Phase 5 — Bastion 외부 스크랩 게시판.

장기 비전: bastion 이 KISA·KrCERT·HackerNews·CVE feed·GitHub trending 을 주기 크롤링,
KG 와 매칭해 교과 연관성 판단, 관리자 게시판에 ScrapPost 로 자동 저장.

본 모듈 baseline:
  - `seed_demo()` 로 3개 데모 ScrapPost 삽입 (idempotent on source_url)
  - `fetch_hn_top(n)` 로 HackerNews top stories 중 보안 키워드 매칭한 것 추출
  - 관리자 승인 시 `services.scenario_jobs.start_job` 으로 시나리오 생성 트리거

장기적으로 swap-out:
  - bastion KG client (kg_recorder/kg_context) 가 정합성 + 교육 가치 점수 부여
  - 한국 컨텍스트 (KISA, ISMS-P, 정통망법) crawler 추가
"""
from __future__ import annotations
import datetime as dt
import logging
import re
from typing import Any
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import ScrapPost

log = logging.getLogger(__name__)

DEMO_POSTS: list[dict[str, Any]] = [
    {
        "source": "krcert",
        "source_url": "https://www.krcert.or.kr/data/secNoticeList.do",
        "title": "KrCERT — Citrix NetScaler ADC/Gateway zero-day 활성 익스플로잇 (CVE-2026-1234 가상)",
        "summary": "Citrix NetScaler 의 NSIP 인터페이스 인증 우회로 RCE 가능. 한국 내 다수 금융권 노출. "
                   "공격 패턴: POST /nsidp/login, Cookie 조작, /netscaler/portal/ 경로 LFI. ModSecurity 룰 #946100 변형 필요.",
        "relevance": {"keywords": ["citrix", "rce", "auth-bypass", "kr"], "education_score": 0.85,
                       "kg_match": ["course3-web-vuln/week04", "course5-soc/week08"]},
    },
    {
        "source": "hackernews",
        "source_url": "https://news.ycombinator.com/item?id=demo-39450000",
        "title": "Mythos AI Worm: prompt-injection 자율 전파 PoC 공개",
        "summary": "오픈소스 LLM 에이전트가 이메일·메신저·코드 PR 채널을 자율 침투해 prompt 를 자기복제하는 PoC. "
                   "OWASP LLM01 (Prompt Injection) + LLM10 (Model Theft) 결합 사례. "
                   "교육 가치: AI 공격면 신규, 학생들이 반드시 인지해야 할 위협 모델.",
        "relevance": {"keywords": ["llm", "prompt-injection", "ai-worm"], "education_score": 0.92,
                       "kg_match": ["course7-ai-security/week11", "course15-ai-safety-advanced/week03"]},
    },
    {
        "source": "github-advisory",
        "source_url": "https://github.com/advisories/GHSA-demo-fastapi-csrf",
        "title": "FastAPI CSRF middleware 우회 (CVE-2026-2222 가상)",
        "summary": "fastapi-csrf-protect 0.x 의 origin/referer 비교가 대소문자 strict — 학생 PoC 가 가능한 헤더 조작 우회. "
                   "신규 학기 web-vuln 실습에 적합.",
        "relevance": {"keywords": ["csrf", "fastapi", "header-bypass"], "education_score": 0.71,
                       "kg_match": ["course3-web-vuln/week06"]},
    },
]


SECURITY_KEYWORDS = re.compile(
    r"(cve|vuln|exploit|rce|sqli|xss|csrf|ransomware|phishing|llm|prompt[- ]?injection|"
    r"zero[- ]?day|backdoor|breach|auth[- ]?bypass|escalation|deserial|sso|oauth)",
    re.I,
)


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


async def seed_demo(session: AsyncSession) -> int:
    """idempotent on source_url. 반환: 새로 추가된 row 수."""
    inserted = 0
    for p in DEMO_POSTS:
        existing = await session.scalar(
            select(ScrapPost).where(ScrapPost.source_url == p["source_url"])
        )
        if existing:
            continue
        session.add(ScrapPost(
            source=p["source"],
            source_url=p["source_url"],
            title=p["title"],
            summary=p["summary"],
            relevance=p["relevance"],
            status="pending",
        ))
        inserted += 1
    if inserted:
        await session.commit()
        log.info("seed_demo inserted %d ScrapPosts", inserted)
    return inserted


async def fetch_hn_top(session: AsyncSession, *, n: int = 10) -> int:
    """HackerNews top story 중 보안 키워드 매칭한 것만 ScrapPost 로 저장.

    네트워크 제약 환경에서는 실패해도 silent (반환 0). idempotent on source_url.
    """
    top_url = "https://hacker-news.firebaseio.com/v0/topstories.json"
    inserted = 0
    try:
        async with httpx.AsyncClient(timeout=8.0) as c:
            r = await c.get(top_url)
            ids = r.json()[: max(1, n * 3)]
            for sid in ids:
                if inserted >= n:
                    break
                item_url = f"https://hacker-news.firebaseio.com/v0/item/{sid}.json"
                ir = await c.get(item_url)
                item = ir.json() or {}
                title = item.get("title") or ""
                story_url = item.get("url") or f"https://news.ycombinator.com/item?id={sid}"
                if not SECURITY_KEYWORDS.search(title):
                    continue
                existing = await session.scalar(
                    select(ScrapPost).where(ScrapPost.source_url == story_url)
                )
                if existing:
                    continue
                session.add(ScrapPost(
                    source="hackernews",
                    source_url=story_url,
                    title=title[:400],
                    summary=item.get("text", "")[:1000] or title[:1000],
                    relevance={
                        "keywords": SECURITY_KEYWORDS.findall(title),
                        "score": item.get("score", 0),
                        "by": item.get("by", ""),
                    },
                    status="pending",
                ))
                inserted += 1
    except Exception as e:
        log.warning("fetch_hn_top failed: %s", e)
        return 0
    if inserted:
        await session.commit()
        log.info("fetch_hn_top inserted %d ScrapPosts", inserted)
    return inserted
