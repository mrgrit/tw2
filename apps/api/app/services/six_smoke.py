"""6v6 인프라 헬스 검증 — TCP probe + Bastion API + Portal API.

각 학생의 6v6 는 docker-compose `.env` 로 호스트 포트를 override 가능하다
(예: PORT_HTTP=18080, PORT_BASTION_API=19100). 등록 시 port_map 을 받고,
미지정 항목은 README default 사용.
"""
from __future__ import annotations
import asyncio
import socket
from typing import Any
import httpx

from ..schemas import SmokeResult

DEFAULT_PORTS: dict[str, int] = {
    "http": 80,
    "https": 443,
    "bastion_ssh": 2204,
    "attacker_ssh": 2202,        # attacker (insider, 내부 발판)
    "attacker_ext_ssh": 2203,    # attacker-ext (outsider, 망 외부 침입자, 2026-06 신규)
    "portal": 8000,
    "siem_lite": 5601,
    "bastion_api": 9100,
}

# (label, key, required) — required = battle 진행에 *반드시* 필요한 표면.
#  attacker SSH (Red 발사대) + bastion API (orchestration) 두 개로 충분.
#  나머지는 학습용 viewer 라 옵셔널 — 6v6 시작 직후 일부 컨테이너가 늦게 뜨는 점도 고려.
PORT_SPEC: list[tuple[str, str, bool]] = [
    ("http", "http", False),
    ("https", "https", False),
    ("bastion-ssh", "bastion_ssh", False),
    ("attacker-ssh", "attacker_ssh", True),
    ("attacker-ext-ssh", "attacker_ext_ssh", False),   # 외부 attacker — 옵셔널(SKIP_ATTACKER_EXT 가능)
    ("portal", "portal", False),
    ("siem-lite", "siem_lite", False),
    ("bastion-api", "bastion_api", True),
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


async def _bastion_health(ip: str, port: int, api_key: str, timeout: float = 5.0) -> dict[str, Any]:
    """6v6 bastion API health 호출."""
    url = f"http://{ip}:{port}/health"
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


def resolve_ports(port_map: dict[str, int] | None) -> dict[str, int]:
    out = dict(DEFAULT_PORTS)
    if port_map:
        for k, v in port_map.items():
            if k in DEFAULT_PORTS and isinstance(v, int) and 1 <= v <= 65535:
                out[k] = v
    return out


async def run_smoke(ip: str, bastion_api_key: str, port_map: dict[str, int] | None = None) -> SmokeResult:
    checks: list[dict[str, Any]] = []
    ports = resolve_ports(port_map)

    probes = await asyncio.gather(*[_tcp_probe(ip, ports[k]) for _, k, _ in PORT_SPEC])
    required_ok = True
    for (label, key, required), ok in zip(PORT_SPEC, probes):
        checks.append({
            "check": "tcp", "label": label, "port": ports[key],
            "required": required, "ok": ok,
        })
        if required and not ok:
            required_ok = False

    bastion = await _bastion_health(ip, ports["bastion_api"], bastion_api_key)
    bastion["check"] = "bastion-api"
    checks.append(bastion)
    if bastion.get("status_code") != 200:
        required_ok = False

    summary = "all required ports + bastion API healthy" if required_ok else "one or more required checks failed"
    return SmokeResult(ok=required_ok, checks=checks, summary=summary)
