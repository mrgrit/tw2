"""실 OpenSearch + Dashboards HTTP 클라이언트 (siem_export 용).

OPENSEARCH_URL 이 설정된 경우에만 생성된다(미설정 시 siem_export 가 no-op).
모든 ensure_* 는 멱등 — 존재 확인 후 없을 때만 생성. 실패는 로깅 후 False/0 반환
(플랫폼 로직을 막지 않음). 테스트는 in-memory Fake 를 쓰므로 이 모듈은 실 환경 전용.
"""
from __future__ import annotations
import json
import logging
from typing import Any
import httpx

log = logging.getLogger(__name__)


class OpenSearchHttpClient:
    def __init__(self, os_url: str, dashboards_url: str, user: str, password: str,
                 *, timeout: float = 8.0) -> None:
        self.os_url = os_url.rstrip("/")
        self.dashboards_url = dashboards_url.rstrip("/")
        self.auth = (user, password)
        self.timeout = timeout

    def _os(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=self.timeout, auth=self.auth, verify=False)

    def _dash(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=self.timeout, auth=self.auth, verify=False,
                                 headers={"osd-xsrf": "true"})

    async def ensure_index(self, index: str) -> bool:
        try:
            async with self._os() as c:
                r = await c.head(f"{self.os_url}/{index}")
                if r.status_code == 200:
                    return False
                await c.put(f"{self.os_url}/{index}")
                return True
        except Exception as e:
            log.warning("ensure_index %s failed: %s", index, e)
            return False

    async def bulk_index(self, index: str, docs: list[dict]) -> int:
        if not docs:
            return 0
        lines = []
        for d in docs:
            lines.append(json.dumps({"index": {"_index": index}}))
            lines.append(json.dumps(d, default=str))
        body = "\n".join(lines) + "\n"
        try:
            async with self._os() as c:
                r = await c.post(f"{self.os_url}/_bulk", content=body,
                                 headers={"content-type": "application/x-ndjson"})
                return len(docs) if r.status_code < 300 else 0
        except Exception as e:
            log.warning("bulk_index %s failed: %s", index, e)
            return 0

    async def ensure_saved_object(self, otype: str, oid: str, attributes: dict) -> bool:
        try:
            async with self._dash() as c:
                r = await c.get(f"{self.dashboards_url}/api/saved_objects/{otype}/{oid}")
                if r.status_code == 200:
                    return False
                r2 = await c.post(f"{self.dashboards_url}/api/saved_objects/{otype}/{oid}",
                                  json={"attributes": attributes})
                return r2.status_code < 300
        except Exception as e:
            log.warning("ensure_saved_object %s/%s failed: %s", otype, oid, e)
            return False

    async def ensure_role(self, name: str, index_pattern: str) -> bool:
        body = {"index_permissions": [{
            "index_patterns": [index_pattern],
            "allowed_actions": ["read", "search", "indices:data/read/*"],
        }]}
        try:
            async with self._os() as c:
                r = await c.get(f"{self.os_url}/_plugins/_security/api/roles/{name}")
                if r.status_code == 200:
                    return False
                r2 = await c.put(f"{self.os_url}/_plugins/_security/api/roles/{name}", json=body)
                return r2.status_code < 300
        except Exception as e:
            log.warning("ensure_role %s failed: %s", name, e)
            return False

    async def search(self, index: str, body: dict) -> list[dict]:
        """index(또는 패턴)에 _search → _source 목록. 없거나 오류면 빈 리스트."""
        try:
            async with self._os() as c:
                r = await c.post(f"{self.os_url}/{index}/_search", json=body)
                if r.status_code >= 300:
                    return []
                hits = (r.json().get("hits") or {}).get("hits") or []
                return [h.get("_source") or {} for h in hits]
        except Exception as e:
            log.warning("search %s failed: %s", index, e)
            return []

    async def ensure_role_mapping(self, role: str, users: list[str]) -> bool:
        body = {"users": users or [], "backend_roles": [f"instructor-{role}"]}
        try:
            async with self._os() as c:
                r = await c.get(f"{self.os_url}/_plugins/_security/api/rolesmapping/{role}")
                if r.status_code == 200:
                    return False
                r2 = await c.put(f"{self.os_url}/_plugins/_security/api/rolesmapping/{role}",
                                 json=body)
                return r2.status_code < 300
        except Exception as e:
            log.warning("ensure_role_mapping %s failed: %s", role, e)
            return False
