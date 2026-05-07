"""6v6 인프라 (학생 VM) 와의 HTTP 클라이언트 — Bastion API + Portal.

학생 VM 의 외부 IP + 자격을 이용해 다음 호출:
  GET  http://<ip>:9100/health           (Bastion)
  POST http://<ip>:9100/run              (Bastion — 명령 실행, 옵션)
  GET  http://<ip>:8000/api/health       (Portal)

호출은 모두 timeout 보호. 실패는 dict 로 반환 (raise 하지 않음). Phase 4 의 monitor 가
주기적으로 호출해서 BattleEvent 로 변환.
"""
from __future__ import annotations
import logging
from typing import Any
import httpx

log = logging.getLogger(__name__)
DEFAULT_TIMEOUT = 5.0


class SixClient:
    def __init__(self, ip: str, bastion_api_key: str, *, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.ip = ip
        self.api_key = bastion_api_key
        self.timeout = timeout

    @property
    def _bastion_base(self) -> str:
        return f"http://{self.ip}:9100"

    @property
    def _portal_base(self) -> str:
        return f"http://{self.ip}:8000"

    async def bastion_health(self) -> dict[str, Any]:
        return await self._get(f"{self._bastion_base}/health", with_key=True)

    async def portal_health(self) -> dict[str, Any]:
        return await self._get(f"{self._portal_base}/", with_key=False)

    async def bastion_run(self, command: str) -> dict[str, Any]:
        """Bastion API 의 명령 실행 endpoint (6v6 가 지원하는 경우).

        Phase 2 의 호출 경로 stub — 실제 6v6 Bastion API 의 `/run` 시그니처 확정 후
        dict 매핑 정밀화. 현재는 raw dict 반환.
        """
        return await self._post(f"{self._bastion_base}/run", {"command": command}, with_key=True)

    async def _get(self, url: str, *, with_key: bool) -> dict[str, Any]:
        headers = {"X-API-Key": self.api_key} if with_key else {}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as c:
                r = await c.get(url, headers=headers)
                return _wrap(url, r)
        except Exception as e:
            return {"url": url, "ok": False, "error": f"{type(e).__name__}: {e}"}

    async def _post(self, url: str, json_body: dict, *, with_key: bool) -> dict[str, Any]:
        headers = {"X-API-Key": self.api_key} if with_key else {}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as c:
                r = await c.post(url, headers=headers, json=json_body)
                return _wrap(url, r)
        except Exception as e:
            return {"url": url, "ok": False, "error": f"{type(e).__name__}: {e}"}


def _wrap(url: str, r: httpx.Response) -> dict[str, Any]:
    body: Any
    ct = r.headers.get("content-type", "")
    if "json" in ct:
        try:
            body = r.json()
        except Exception:
            body = r.text[:500]
    else:
        body = r.text[:500]
    return {"url": url, "ok": 200 <= r.status_code < 300, "status_code": r.status_code, "body": body}
