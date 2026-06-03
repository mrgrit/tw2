#!/usr/bin/env python3
"""테스트/e2e 용 mock 6v6 Assessor.

POST /assess 를 받아 모든 check 를 passed=True (또는 env MOCK_ASSESS_PASS=0 이면 false)
로 응답한다. 실 6v6 Assessor 없이 cohort_cross_infra e2e 를 돌리기 위한 stub.
부작용 0 — 받은 check-spec 을 그대로 evidence 로 echo.

사용: MOCK_ASSESS_PORT=9399 python3 scripts/mock_assessor.py
"""
from __future__ import annotations
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PASS = os.getenv("MOCK_ASSESS_PASS", "1") not in ("0", "false", "no")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # noqa: D401 - 조용히
        pass

    def _send(self, obj):
        payload = json.dumps(obj).encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        length = int(self.headers.get("content-length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw or b"{}")
        except Exception:
            body = {}
        path = self.path.split("?")[0]

        if path == "/activity":
            # 데모: 실패 명령 다수 → 병목(repeated_failed_commands) 유발 → 피드백 트리거.
            self._send({
                "collected_at": "mock",
                "commands": [{"cmd": f"sqlmap -u http://target try{i}", "rc": 1, "stderr": "error"}
                             for i in range(4)] + [{"cmd": "nmap -sV target", "rc": 0}],
                "fim": [{"path": "/var/www/html/shell.php", "change": "added"}],
                "alerts": [{"rule_id": 31108, "desc": "ModSecurity SQLi"}],
                "services": {"apache2": "running", "wazuh-agent": "running"},
            })
            return
        if path == "/provision-rule":
            self._send({"ok": True, "action": (body or {}).get("action"), "applied": True})
            return

        # 기본: /assess
        checks = body.get("checks", []) if isinstance(body, dict) else []
        results = [{
            "id": c.get("id"),
            "passed": PASS,
            "evidence": f"[mock] {c.get('type')} on {c.get('target')} → {'OK' if PASS else 'MISS'}: {c.get('params')}",
            "raw": {"mock": True, "type": c.get("type")},
        } for c in checks]
        self._send({"collected_at": "mock", "results": results})


if __name__ == "__main__":
    port = int(os.getenv("MOCK_ASSESS_PORT", "9399"))
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"mock assessor on 127.0.0.1:{port} (pass={PASS})", flush=True)
    srv.serve_forever()
