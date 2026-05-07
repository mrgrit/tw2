"""인-메모리 sliding-window rate limiter (Phase 8).

Phase 8 범위: 단일 노드 inmem 으로 충분 (multi-replica 시 redis 백엔드로 교체).
- signup: per-IP 5 / 5분
- login : per-IP 10 / 5분 + per-email 5 / 5분 (이메일 enumeration 완화)

테스트 모드 (`TUBEWAR_RATE_LIMIT_DISABLE=1`) 면 enforce 가 no-op.
"""
from __future__ import annotations
import collections
import os
import threading
import time
from typing import Deque

from fastapi import HTTPException, Request, status

_lock = threading.Lock()
_buckets: dict[str, Deque[float]] = collections.defaultdict(collections.deque)


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _disabled() -> bool:
    return os.getenv("TUBEWAR_RATE_LIMIT_DISABLE", "").lower() in ("1", "true", "yes")


def _hit(key: str, limit: int, window_sec: float) -> tuple[bool, float]:
    """key 의 현재 호출을 기록하고, 허용 여부 + retry_after 를 반환."""
    now = time.monotonic()
    cutoff = now - window_sec
    with _lock:
        bucket = _buckets[key]
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= limit:
            retry = window_sec - (now - bucket[0])
            return False, max(retry, 0.5)
        bucket.append(now)
        return True, 0.0


def reset() -> None:
    """테스트용 — 모든 bucket clear."""
    with _lock:
        _buckets.clear()


def enforce_signup(request: Request) -> None:
    if _disabled():
        return
    ip = _client_ip(request)
    ok, retry = _hit(f"signup:ip:{ip}", limit=5, window_sec=300)
    if not ok:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail="signup rate limit exceeded",
            headers={"Retry-After": str(int(retry) + 1)},
        )


def enforce_login(request: Request, *, email: str) -> None:
    if _disabled():
        return
    ip = _client_ip(request)
    ok_ip, retry_ip = _hit(f"login:ip:{ip}", limit=10, window_sec=300)
    if not ok_ip:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail="login rate limit exceeded (ip)",
            headers={"Retry-After": str(int(retry_ip) + 1)},
        )
    ok_em, retry_em = _hit(f"login:email:{email}", limit=5, window_sec=300)
    if not ok_em:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail="login rate limit exceeded (email)",
            headers={"Retry-After": str(int(retry_em) + 1)},
        )
