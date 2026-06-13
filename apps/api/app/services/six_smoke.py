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

# (label, key, required, vhost) — required = battle 진행에 *반드시* 필요한 표면.
#  attacker SSH (Red 발사대) + bastion API (orchestration) 두 개로 충분.
#  나머지는 학습용 viewer 라 옵셔널 — 6v6 시작 직후 일부 컨테이너가 늦게 뜨는 점도 고려.
#  vhost != None: 해당 서비스는 포트를 직접 publish 하지 않고 80 리버스프록시(Host 헤더)로
#  라우팅하는 6v6 모델일 수 있어, 직접 TCP 실패 시 vhost 로 폴백 확인한다.
PORT_SPEC: list[tuple[str, str, bool, str | None]] = [
    ("http", "http", False, None),
    ("https", "https", False, None),
    ("bastion-ssh", "bastion_ssh", False, None),
    ("attacker-ssh", "attacker_ssh", True, None),
    ("attacker-ext-ssh", "attacker_ext_ssh", False, None),   # 외부 attacker — 옵셔널(SKIP_ATTACKER_EXT 가능)
    ("portal", "portal", False, "portal.6v6.lab"),
    ("siem-lite", "siem_lite", False, "siem-lite.6v6.lab"),
    ("bastion-api", "bastion_api", True, None),
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


async def _vhost_probe(ip: str, http_port: int, vhost: str, timeout: float = 4.0) -> bool:
    """80 리버스프록시 vhost 로 서비스 도달 확인.

    8000/5601 을 직접 publish 하지 않고 Host 헤더(`portal.6v6.lab` 등)로 라우팅하는
    6v6 모델 대응. 프록시가 응답(상태<500)하면 백엔드가 살아 있다고 본다(502/503=백엔드 down).
    """
    url = f"http://{ip}:{http_port}/"
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            r = await client.get(url, headers={"Host": vhost})
            return r.status_code < 500
    except Exception:
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

    async def _probe_one(label: str, key: str, required: bool, vhost: str | None) -> dict[str, Any]:
        ok = await _tcp_probe(ip, ports[key])
        method = "tcp"
        if not ok and vhost:  # 직접 포트 미publish → 80 vhost 라우팅 폴백
            if await _vhost_probe(ip, ports["http"], vhost):
                ok, method = True, f"vhost:{vhost}@{ports['http']}"
        return {"check": method, "label": label, "port": ports[key], "required": required, "ok": ok}

    results = await asyncio.gather(*[_probe_one(l, k, r, v) for l, k, r, v in PORT_SPEC])
    required_ok = True
    for res in results:
        checks.append(res)
        if res["required"] and not res["ok"]:
            required_ok = False

    bastion = await _bastion_health(ip, ports["bastion_api"], bastion_api_key)
    bastion["check"] = "bastion-api"
    checks.append(bastion)
    if bastion.get("status_code") != 200:
        required_ok = False

    summary = "all required ports + bastion API healthy" if required_ok else "one or more required checks failed"
    return SmokeResult(ok=required_ok, checks=checks, summary=summary)
