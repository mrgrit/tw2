"""개인 GPU(Ollama) AI 튜터 — 드래그-질문 기능 백엔드.

학생/강사가 개인 프로필에 GPU 서버(Ollama) 주소를 등록하고 모델을 고르면, UI 의
드래그-질문 위젯이 **현재 페이지 맥락 + 드래그한 내용**을 근거로 질의응답을 받는다.

흐름:
  1) POST /llm/models  — {url} 로 Ollama `/api/tags` 프록시 → 모델 목록(연결 테스트 겸용).
  2) POST /llm/settings — 고른 url+model 을 내 계정에 저장.  GET /llm/settings — 조회.
  3) POST /llm/ask     — 저장된 url+model 로 `/api/chat` 호출. system 프롬프트에 페이지
                         경로/제목/본문 발췌 + 드래그한 선택 텍스트를 주입해 맥락형 답변.

GPU 서버는 VPN 너머(예: 211.170.162.139:10934)일 수 있어, API 호스트에서 VPN 이 올라와
있어야 실제 응답이 온다. 미설정/도달불가 시 명확한 오류를 반환한다.
"""
from __future__ import annotations
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..db import get_session
from ..models import User
from ..security import get_current_user

router = APIRouter(prefix="/llm", tags=["llm"])


def _norm_url(url: str) -> str:
    url = (url or "").strip().rstrip("/")
    if url and not url.startswith(("http://", "https://")):
        url = "http://" + url
    return url


# ── 1) 모델 목록(연결 테스트) ─────────────────────────────────────────────────
class LLMConnectIn(BaseModel):
    url: str = Field(min_length=1, max_length=255)


@router.post("/models")
async def llm_models(
    body: LLMConnectIn,
    user: User = Depends(get_current_user),  # noqa: ARG001 — 인증만 강제(누구 것이든 조회 가능)
) -> dict[str, Any]:
    """Ollama 서버에서 `ollama list`(= /api/tags) 결과를 가져와 모델명 배열로 반환."""
    url = _norm_url(body.url)
    if not url:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "url 이 비었습니다.")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(f"{url}/api/tags")
        models = [m.get("name") for m in r.json().get("models", []) if m.get("name")]
        return {"connected": True, "url": url, "models": models}
    except Exception as e:  # 연결 실패도 200 으로 알려 UI 가 안내(VPN 미연결 등)
        return {"connected": False, "url": url, "models": [], "error": f"{type(e).__name__}: {e}"}


# ── 2) 내 설정 저장/조회 ──────────────────────────────────────────────────────
class LLMSettingsIn(BaseModel):
    url: str = Field(min_length=1, max_length=255)
    model: str = Field(min_length=1, max_length=120)


class LLMSettingsOut(BaseModel):
    url: str | None = None
    model: str | None = None


@router.get("/settings", response_model=LLMSettingsOut)
async def get_llm_settings(user: User = Depends(get_current_user)) -> LLMSettingsOut:
    return LLMSettingsOut(url=user.llm_url, model=user.llm_model)


@router.post("/settings", response_model=LLMSettingsOut)
async def save_llm_settings(
    body: LLMSettingsIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> LLMSettingsOut:
    user.llm_url = _norm_url(body.url)
    user.llm_model = body.model.strip()
    session.add(user)
    await session.commit()
    return LLMSettingsOut(url=user.llm_url, model=user.llm_model)


# ── 3) 드래그-질문 (맥락형 채팅) ──────────────────────────────────────────────
class AskContext(BaseModel):
    page: str = ""           # location.pathname
    title: str = ""          # document.title
    page_content: str = ""   # main innerText 발췌
    selection: str = ""      # 드래그한 텍스트


class AskTurn(BaseModel):
    role: str
    content: str


class LLMAskIn(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    context: AskContext = AskContext()
    history: list[AskTurn] = []


def _build_system_prompt(user: User, ctx: AskContext) -> str:
    s = get_settings()
    parts = [
        "너는 tubewar — 학생 간 6v6 사이버 공방전(레드/블루) 교육 플랫폼의 AI 튜터다.",
        "학생의 질문에 친절하고 정확하게, 한국어로 간결·실용적으로 답한다.",
        "보안 실습 맥락(공격/방어 기법, 로그·룰·페이로드 해석)을 이해하고 설명한다.",
        f"\n현재 사용자: {user.name} (role: {user.role})",
        f"현재 페이지: {ctx.page or '-'}" + (f" — {ctx.title}" if ctx.title else ""),
    ]
    if ctx.selection.strip():
        parts.append(
            "\n[학생이 드래그(선택)한 내용 — 질문의 핵심 대상]\n"
            f"{ctx.selection.strip()[:2000]}\n"
            "위 선택 내용을 우선 근거로 삼아 설명하라."
        )
    if ctx.page_content.strip():
        parts.append(
            "\n[현재 페이지 본문 발췌 — 보조 맥락]\n"
            f"{ctx.page_content.strip()[:4000]}\n"
            "선택 내용이 가리키는 맥락을 위 본문에서 찾아 구체적으로(명령/룰/구문 단위) 설명하라."
        )
    parts.append(f"\n(참고 플랫폼 기본 모델 폴백: {s.llm_model})")
    return "\n".join(parts)


@router.post("/ask")
async def llm_ask(
    body: LLMAskIn,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """저장된 개인 GPU(Ollama)로 맥락형 질의응답. 미설정이면 400 으로 안내."""
    s = get_settings()
    url = _norm_url(user.llm_url or "")
    model = (user.llm_model or "").strip()
    if not url or not model:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "GPU 서버가 설정되지 않았습니다. 내 프로필 → 'AI 모델(GPU 서버)' 에서 연결·모델 선택 후 저장하세요.",
        )

    messages: list[dict[str, str]] = [{"role": "system", "content": _build_system_prompt(user, body.context)}]
    for h in body.history[-10:]:
        if h.role in ("user", "assistant") and h.content:
            messages.append({"role": h.role, "content": h.content[:1000]})
    messages.append({"role": "user", "content": body.question})

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(f"{url}/api/chat", json={
                "model": model,
                "messages": messages,
                "stream": False,
                "options": {"temperature": 0.4, "num_predict": 900},
            })
        if r.status_code >= 400:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                                f"Ollama 오류 {r.status_code}: {r.text[:200]}")
        reply = (r.json().get("message") or {}).get("content") or "응답을 생성하지 못했습니다."
        return {"reply": reply, "model": model}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            f"GPU 서버 연결 실패({type(e).__name__}). VPN 연결과 서버 주소를 확인하세요: {str(e)[:160]}",
        )
