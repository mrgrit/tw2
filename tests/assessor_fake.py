"""테스트용 Fake Assessor — 실 6v6 없이 /assess 응답을 시뮬레이션.

두 가지 사용 방식 제공:

1) `make_fake_assessor_app(policy)` + httpx ASGITransport
   실제 HTTP 경로(URL/Host/X-API-Key/JSON 파싱)를 검증하고 싶을 때.
   assessor_client.assess(infra, checks, client=fake_client) 로 주입.

2) `build_fake_assess(policy)` → async 함수
   auto_monitor/grader/cross-infra 테스트에서 `assessor_client.assess` 를 monkeypatch
   할 drop-in. 실제 네트워크/HTTP 없이 check-spec → results 로 변환.

policy: check-spec → (passed, evidence) 결정.
  - dict[str|callable] 또는 callable(check)->(passed, evidence)
  - 기본: 모든 check passed=True, evidence 자동 생성.
"""
from __future__ import annotations
from typing import Any, Callable

from fastapi import FastAPI, Header, HTTPException, Request

# (passed, evidence) 를 돌려주는 정책 타입
Policy = Callable[[dict[str, Any]], tuple[bool, str]]


def _default_policy(check: dict[str, Any]) -> tuple[bool, str]:
    t = check.get("type", "?")
    params = check.get("params", {})
    return True, f"[{t}] satisfied: {params}"


def _coerce_policy(policy) -> Policy:
    if policy is None:
        return _default_policy
    if callable(policy):
        return policy

    # dict: key=check id 또는 type → bool 또는 (bool, evidence)
    def fn(check: dict[str, Any]) -> tuple[bool, str]:
        key = check.get("id")
        if key not in policy:
            key = check.get("type")
        if key not in policy:
            return _default_policy(check)
        val = policy[key]
        if isinstance(val, tuple):
            return bool(val[0]), str(val[1])
        passed = bool(val)
        return passed, (f"[{check.get('type')}] {'pass' if passed else 'fail'}")
    return fn


def simulate_results(checks: list[dict[str, Any]], policy=None) -> list[dict[str, Any]]:
    fn = _coerce_policy(policy)
    out: list[dict[str, Any]] = []
    for c in checks or []:
        passed, evidence = fn(c)
        out.append({
            "id": c.get("id"),
            "passed": passed,
            "evidence": evidence,
            "raw": {"type": c.get("type"), "target": c.get("target")},
        })
    return out


def make_fake_assessor_app(policy=None, *, require_key: str | None = None,
                           require_host: str | None = "assessor.6v6.lab",
                           activity=None) -> FastAPI:
    """mock ASGI 앱 — /assess + /activity + /provision-rule.

    activity: /activity 응답 dict(commands/fim/alerts/services) 또는 callable(body)->dict.
    """
    app = FastAPI()

    def _guard(x_api_key, host):
        if require_key is not None and x_api_key != require_key:
            raise HTTPException(401, "bad api key")
        if require_host is not None and host != require_host:
            raise HTTPException(400, f"bad host: {host}")

    @app.post("/assess")
    async def assess(request: Request,
                     x_api_key: str | None = Header(default=None),
                     host: str | None = Header(default=None)):
        _guard(x_api_key, host)
        body = await request.json()
        return {
            "collected_at": "2026-06-03T00:00:00Z",
            "results": simulate_results(body.get("checks", []), policy),
        }

    @app.post("/activity")
    async def activity_ep(request: Request,
                          x_api_key: str | None = Header(default=None),
                          host: str | None = Header(default=None)):
        _guard(x_api_key, host)
        body = await request.json()
        act = activity(body) if callable(activity) else (activity or {})
        return {
            "collected_at": "2026-06-03T00:00:00Z",
            "commands": act.get("commands", []),
            "fim": act.get("fim", []),
            "alerts": act.get("alerts", []),
            "services": act.get("services", {}),
        }

    @app.post("/provision-rule")
    async def provision(request: Request,
                        x_api_key: str | None = Header(default=None),
                        host: str | None = Header(default=None)):
        _guard(x_api_key, host)
        body = await request.json()
        return {"ok": True, "action": body.get("action"), "applied": True}

    return app


def build_fake_activity(payload=None, *, calls: list | None = None):
    """`assessor_client.activity` 를 대체할 async 함수."""
    async def fake_activity(infra, *, since_sec=120, limit=200, want=None, filter=None,
                            timeout=8.0, client=None):
        if calls is not None:
            calls.append({"vm_ip": getattr(infra, "vm_ip", None), "since_sec": since_sec,
                          "want": want, "filter": filter})
        p = payload(infra) if callable(payload) else (payload or {})
        return {
            "ok": True, "collected_at": "2026-06-03T00:00:00Z",
            "commands": p.get("commands", []), "fim": p.get("fim", []),
            "alerts": p.get("alerts", []), "services": p.get("services", {}),
            "url": f"http://{getattr(infra, 'vm_ip', '?')}/activity",
        }
    return fake_activity


def build_fake_assess(policy=None, *, calls: list | None = None):
    """`assessor_client.assess` 를 대체할 async 함수.

    calls 리스트를 주면 (infra, checks, battle_id) 호출 내역을 기록한다(검증용).
    """
    async def fake_assess(infra, checks, *, battle_id=None, timeout=8.0, client=None):
        if calls is not None:
            calls.append({
                "vm_ip": getattr(infra, "vm_ip", None),
                "checks": checks,
                "battle_id": battle_id,
            })
        return {
            "ok": True,
            "collected_at": "2026-06-03T00:00:00Z",
            "results": simulate_results(checks, policy),
            "url": f"http://{getattr(infra, 'vm_ip', '?')}/assess",
        }
    return fake_assess
