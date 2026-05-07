"""감사 로그 서비스 — 관리자 행동 + 보안 이벤트 (Phase 8).

- record(session, actor, action, ...) — 단일 helper
- HTTP context (ip / ua) 는 Request 객체에서 추출
- 실패해도 본 작업은 막지 않음 (best-effort)
"""
from __future__ import annotations
import logging
from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AuditLog, User

log = logging.getLogger("tubewar.audit")


def _client_ip(request: Request | None) -> str | None:
    if request is None:
        return None
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


def _user_agent(request: Request | None) -> str | None:
    if request is None:
        return None
    ua = request.headers.get("user-agent")
    return ua[:255] if ua else None


async def record(
    session: AsyncSession,
    *,
    actor: User | None,
    action: str,
    target_type: str | None = None,
    target_id: str | int | None = None,
    detail: dict[str, Any] | None = None,
    request: Request | None = None,
    actor_email: str | None = None,
) -> None:
    try:
        row = AuditLog(
            actor_user_id=actor.id if actor else None,
            actor_email=(actor.email if actor else actor_email),
            action=action[:80],
            target_type=(target_type or "")[:40] or None,
            target_id=(str(target_id) if target_id is not None else None),
            ip=_client_ip(request),
            user_agent=_user_agent(request),
            detail=dict(detail or {}),
        )
        session.add(row)
        await session.commit()
    except Exception:
        log.exception("audit record failed action=%s", action)
        try:
            await session.rollback()
        except Exception:
            pass
