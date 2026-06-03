"""6v6 Assessor (`/assess`) HTTP 클라이언트 — six_client 패턴.

Assessor 는 6v6 의 **읽기 전용** 채점 표면이다. tubewar 는 check-spec[] 을 보내고
결과(passed/evidence)를 받는다. 부작용 0.

계약:
  POST http://{vm_ip}/assess
    header  Host: assessor.6v6.lab,  X-API-Key: <key>
    body    {"battle_id"?, "checks":[{"id","type","target","params"}]}
  resp      {"collected_at", "results":[{"id","passed","evidence","raw"?}]}

URL 해석: infra.port_map['assessor'] 가 있으면 직접 포트(`http://{ip}:{port}/assess`)를
우선한다. 없으면 80 포트 + Host 헤더로 vhost 라우팅한다.

실패는 **dict 로 반환**(raise 하지 않음) — six_client 와 동일. auto_monitor/dry_run 이
주기적으로 호출하므로 절대 예외로 죽지 않아야 한다.
"""
from __future__ import annotations
import logging
from typing import Any
import httpx

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 8.0
ASSESSOR_HOST = "assessor.6v6.lab"


def resolve_base(infra: Any) -> str:
    """Assessor base URL. port_map['assessor'] 우선 → 없으면 80 포트(+Host 헤더)."""
    port_map = getattr(infra, "port_map", None) or {}
    port = port_map.get("assessor")
    if port:
        return f"http://{infra.vm_ip}:{int(port)}"
    return f"http://{infra.vm_ip}"


def resolve_url(infra: Any, path: str = "/assess") -> str:
    """엔드포인트 URL. 기본 `/assess` (하위호환)."""
    return resolve_base(infra) + path


def resolve_headers(infra: Any) -> dict[str, str]:
    return {
        "Host": ASSESSOR_HOST,
        "X-API-Key": getattr(infra, "bastion_api_key", "") or "",
        "content-type": "application/json",
    }


def _normalize_results(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    results = data.get("results")
    if not isinstance(results, list):
        return []
    out: list[dict[str, Any]] = []
    for r in results:
        if not isinstance(r, dict):
            continue
        out.append({
            "id": r.get("id"),
            "passed": bool(r.get("passed")),
            "evidence": r.get("evidence") or "",
            "raw": r.get("raw"),
        })
    return out


async def assess(
    infra: Any,
    checks: list[dict[str, Any]],
    *,
    battle_id: int | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """check-spec[] 을 Assessor 로 보내고 결과를 받는다.

    반환:
      성공 → {"ok": True, "collected_at": ..., "results": [{id,passed,evidence,raw}], "url": ...}
      실패 → {"ok": False, "error": "...", "results": [], "url": ...}

    `client` 가 주어지면(테스트) 그것을 사용(닫지 않음). 없으면 일회용 클라이언트 생성.
    """
    url = resolve_url(infra)
    headers = resolve_headers(infra)
    body: dict[str, Any] = {"checks": checks or []}
    if battle_id is not None:
        body["battle_id"] = battle_id

    own_client = client is None
    c = client or httpx.AsyncClient(timeout=timeout)
    try:
        r = await c.post(url, headers=headers, json=body)
        ok = 200 <= r.status_code < 300
        ct = r.headers.get("content-type", "")
        data = r.json() if "json" in ct else {}
        if not ok:
            return {"ok": False, "error": f"http {r.status_code}", "results": [],
                    "url": url, "status_code": r.status_code}
        return {
            "ok": True,
            "collected_at": data.get("collected_at"),
            "results": _normalize_results(data),
            "url": url,
        }
    except Exception as e:  # 네트워크/timeout/파싱 등 — 절대 raise 안 함
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "results": [], "url": url}
    finally:
        if own_client:
            await c.aclose()


def results_by_id(resp: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """결과를 check id 로 인덱싱."""
    return {r["id"]: r for r in resp.get("results", []) if r.get("id")}


# ── 모니터링: /activity (read-only 활동 pull) ──────────
DEFAULT_WANT = ["commands", "fim", "alerts", "services"]


async def activity(
    infra: Any,
    *,
    since_sec: int = 120,
    limit: int = 200,
    want: list[str] | None = None,
    filter: dict[str, Any] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """학생 infra 의 최근 활동을 read-only 로 pull.

    반환:
      성공 → {"ok": True, "collected_at", "commands":[], "fim":[], "alerts":[], "services":{}, "url"}
      실패 → {"ok": False, "error", "commands":[], "fim":[], "alerts":[], "services":{}, "url"}

    NAT 뒤(인바운드 불가) 환경에서도 동일 시그니처로 push 모드를 끼워넣을 수 있도록
    클라이언트는 infra 만 받는다(URL/transport 는 내부 해석).
    """
    url = resolve_url(infra, "/activity")
    headers = resolve_headers(infra)
    body: dict[str, Any] = {"since_sec": int(since_sec), "limit": int(limit),
                            "want": want or DEFAULT_WANT}
    if filter:
        body["filter"] = filter
    empty = {"commands": [], "fim": [], "alerts": [], "services": {}}
    own_client = client is None
    c = client or httpx.AsyncClient(timeout=timeout)
    try:
        r = await c.post(url, headers=headers, json=body)
        if not (200 <= r.status_code < 300):
            return {"ok": False, "error": f"http {r.status_code}", "url": url,
                    "status_code": r.status_code, **empty}
        data = r.json() if "json" in r.headers.get("content-type", "") else {}
        return {
            "ok": True,
            "collected_at": data.get("collected_at"),
            "commands": data.get("commands") or [],
            "fim": data.get("fim") or [],
            "alerts": data.get("alerts") or [],
            "services": data.get("services") or {},
            "url": url,
        }
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "url": url, **empty}
    finally:
        if own_client:
            await c.aclose()


# ── (옵션) 룰 무장: /provision-rule (별도 write, 6v6 기본 OFF) ──
async def provision_rule(
    infra: Any,
    *,
    action: str,                 # arm | withdraw
    rule: dict[str, Any],
    battle_id: int | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """검증된 룰 템플릿을 6v6 에 무장/회수. 실패는 dict 반환(raise X)."""
    url = resolve_url(infra, "/provision-rule")
    headers = resolve_headers(infra)
    body: dict[str, Any] = {"action": action, "rule": rule}
    if battle_id is not None:
        body["battle_id"] = battle_id
    own_client = client is None
    c = client or httpx.AsyncClient(timeout=timeout)
    try:
        r = await c.post(url, headers=headers, json=body)
        ok = 200 <= r.status_code < 300
        data = r.json() if "json" in r.headers.get("content-type", "") else {}
        return {"ok": ok, "status_code": r.status_code, "result": data, "url": url}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "url": url}
    finally:
        if own_client:
            await c.aclose()
