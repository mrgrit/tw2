"""6v6 인프라 헬스 검증 — TCP probe + Bastion API + Portal API.

`/home/opsclaw/6v6/README.md` 의 외부 노출 포트 표 그대로:
  80   HTTP
  443  HTTPS
  2204 bastion SSH
  2202 attacker SSH
  8000 portal
  5601 siem-lite
  9100 bastion API  (X-API-Key header 검증)

Phase 1 은 *연결성* 만 확인. 실제 SSH 로그인/명령 실행은 Phase 2.
"""
from __future__ import annotations
import asyncio
import socket
from typing import Any
import httpx

from ..schemas import SmokeResult

PORTS = [
    ("http", 80, False),
    ("https", 443, False),
    ("bastion-ssh", 2204, True),
    ("attacker-ssh", 2202, True),
    ("portal", 8000, False),
    ("siem-lite", 5601, False),
    ("bastion-api", 9100, True),
]


async def _tcp_probe(ip: str, port: int, timeout: float = 3.0) -> bool:
    """단일 TCP connect 시도 → 성공 여부."""
    try:
        fut = asyncio.open_connection(ip, port)
        reader, writer = await asyncio.wait_for(fut, timeout=timeout)
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return True
    except (asyncio.TimeoutError, OSError, socket.gaierror):
        return False


async def _bastion_health(ip: str, api_key: str, timeout: float = 5.0) -> dict[str, Any]:
    """6v6 bastion API health 호출."""
    url = f"http://{ip}:9100/health"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(url, headers={"X-API-Key": api_key})
            return {
                "url": url,
                "status_code": r.status_code,
                "body": r.json() if "json" in r.headers.get("content-type", "") else r.text[:300],
            }
    except Exception as e:
        return {"url": url, "error": f"{type(e).__name__}: {e}"}


async def run_smoke(ip: str, bastion_api_key: str) -> SmokeResult:
    checks: list[dict[str, Any]] = []

    probes = await asyncio.gather(*[_tcp_probe(ip, p) for _, p, _ in PORTS])
    required_ok = True
    for (label, port, required), ok in zip(PORTS, probes):
        checks.append({"check": "tcp", "label": label, "port": port, "required": required, "ok": ok})
        if required and not ok:
            required_ok = False

    bastion = await _bastion_health(ip, bastion_api_key)
    bastion["check"] = "bastion-api"
    checks.append(bastion)
    if bastion.get("status_code") != 200:
        required_ok = False

    summary = "all required ports + bastion API healthy" if required_ok else "one or more required checks failed"
    return SmokeResult(ok=required_ok, checks=checks, summary=summary)
