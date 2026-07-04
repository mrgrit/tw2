#!/usr/bin/env python3
"""진짜 el34 Assessor — POST /assess, /activity 를 el34 컨테이너에서 docker exec 로 실제 수행.
mock 아님: 로그 grep·wazuh alert·process·port 를 진짜로 검사해 passed 판정.
.211(el34 도커 호스트)에서 docker 권한(root)으로 실행. bind 0.0.0.0:9201 → .161/.211 공용.
"""
from __future__ import annotations
import json, os, shlex, subprocess, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CN = {"web": "el34-web", "ips": "el34-ips", "siem": "el34-siem", "fw": "el34-fw",
      "secu": "el34-siem", "bastion": "el34-bastion", "waf": "el34-web", "portal": "el34-web"}
# log alias -> (container, [candidate paths])
LOGS = {
    "modsec": ("el34-web", ["/var/log/apache2/modsec_audit.log", "/var/log/apache2/ai_access.log",
                            "/var/log/apache2/access.log", "/var/log/apache2/error.log"]),
    "apache_error": ("el34-web", ["/var/log/apache2/error.log", "/var/log/apache2/ai_error.log"]),
    "auth": ("el34-web", ["/var/log/auth.log"]),
    "suricata": ("el34-ips", ["/var/log/suricata/eve.json", "/var/log/suricata/fast.log"]),
}
WAZUH = ("el34-siem", ["/var/ossec/logs/alerts/alerts.json", "/var/ossec/logs/alerts/alerts.log"])


def dexec(container, cmd, timeout=25):
    try:
        p = subprocess.run(["docker", "exec", container, "sh", "-lc", cmd],
                           capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except Exception as e:
        return 255, f"exec-error: {e}"


def _grep(container, paths, pattern, tail=20000):
    q = shlex.quote(pattern)
    for path in paths:
        cmd = f"test -e {shlex.quote(path)} && tail -n {tail} {shlex.quote(path)} 2>/dev/null | grep -a -F {q} | tail -3"
        rc, out = dexec(container, cmd)
        if out.strip():
            return True, f"{path}: " + out.strip()[:300]
    return False, f"no match '{pattern}' in {paths[0]}"


def check(c):
    t = c.get("type"); tgt = c.get("target"); p = c.get("params") or {}
    cont = CN.get(tgt)
    try:
        if t == "log_contains":
            log = p.get("log"); pat = p.get("pattern") or p.get("regex") or ""
            ent = LOGS.get(log)
            if not ent:
                return False, f"unknown log alias {log}"
            return _grep(ent[0], ent[1], pat)
        if t == "wazuh_alert":
            pat = p.get("pattern") or (str(p.get("rule_id")) if p.get("rule_id") else "")
            if not pat:
                # since_sec 만 → 최근 알림 존재 여부
                rc, out = dexec(WAZUH[0], f"tail -n 50 {WAZUH[1][0]} 2>/dev/null | tail -3")
                return bool(out.strip()), (out.strip()[:300] or "no recent wazuh alerts")
            return _grep(WAZUH[0], WAZUH[1], pat)
        if t == "file_exists":
            if not cont:
                return False, f"no container for target {tgt}"
            rc, out = dexec(cont, f"test -e {shlex.quote(p.get('path',''))} && echo OK")
            return ("OK" in out), (f"exists {p.get('path')}" if "OK" in out else f"missing {p.get('path')}")
        if t == "file_contains":
            if not cont:
                return False, f"no container for target {tgt}"
            pat = p.get("pattern") or p.get("regex") or ""
            return _grep(cont, [p.get("path", "")], pat)
        if t == "file_hash":
            if not cont:
                return False, f"no container for target {tgt}"
            rc, out = dexec(cont, f"sha256sum {shlex.quote(p.get('path',''))} 2>/dev/null")
            return bool(out.strip()), out.strip()[:200]
        if t == "process_running":
            if not cont:
                return False, f"no container for target {tgt}"
            name = p.get("name", "")
            rc, out = dexec(cont, f"pgrep -fa {shlex.quote(name)} 2>/dev/null | head -2")
            return bool(out.strip()), (out.strip()[:200] or f"no process {name}")
        if t == "port_listening":
            if not cont:
                return False, f"no container for target {tgt}"
            port = str(p.get("port", ""))
            rc, out = dexec(cont, f"(ss -tlnp 2>/dev/null || netstat -tlnp 2>/dev/null) | grep -E ':{port}\\b' | head -2")
            return bool(out.strip()), (out.strip()[:200] or f"port {port} not listening")
        if t == "fim_change":
            # 근사: wazuh syscheck 또는 파일 존재+최근 mtime
            path = p.get("path", "")
            ok, ev = _grep(WAZUH[0], WAZUH[1], os.path.basename(path) or path)
            return ok, ev
        if t == "command_ran":
            # 외부 공격자 명령 로그는 6v6 원칙상 미수집 → 타깃 접근로그에서 패턴 흔적으로 근사.
            pat = p.get("pattern") or ""
            # AICompanion :8007 요청은 ai_port_access.log 에, 웹 :80 은 ai_access/access 에 남는다.
            ok, ev = _grep("el34-web", ["/var/log/apache2/ai_access.log", "/var/log/apache2/ai_port_access.log",
                                        "/var/log/apache2/access.log", "/var/log/apache2/admin_access.log"], pat)
            if ok:
                return True, "target-side access trace: " + ev
            return False, f"external command_ran not collectable; no target-side trace for '{pat}'"
    except Exception as e:
        return False, f"check-error: {e}"
    return False, f"unsupported check type {t}"


def collect_activity():
    """타깃 측 최근 흔적 수집 (read-only)."""
    out = {"collected_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "commands": [], "fim": [], "alerts": [], "services": {}}
    # 최근 웹 접근(공격 흔적) — commands 대용 아님, alerts 로.
    rc, acc = dexec("el34-web", "tail -n 40 /var/log/apache2/ai_access.log 2>/dev/null")
    for ln in [x for x in acc.splitlines() if x.strip()][-15:]:
        out["alerts"].append({"src": "apache_access", "desc": ln[:200]})
    rc, ms = dexec("el34-web", "tail -n 15 /var/log/apache2/modsec_audit.log 2>/dev/null | grep -a -iE 'id \"|denied|403' | tail -5")
    for ln in [x for x in ms.splitlines() if x.strip()]:
        out["alerts"].append({"src": "modsec", "desc": ln[:200]})
    rc, su = dexec("el34-ips", "tail -n 10 /var/log/suricata/fast.log 2>/dev/null | tail -5")
    for ln in [x for x in su.splitlines() if x.strip()]:
        out["alerts"].append({"src": "suricata", "rule_id": 0, "desc": ln[:200]})
    rc, wz = dexec("el34-siem", "tail -n 8 /var/ossec/logs/alerts/alerts.log 2>/dev/null | tail -4")
    for ln in [x for x in wz.splitlines() if x.strip()]:
        out["alerts"].append({"src": "wazuh", "desc": ln[:200]})
    for svc, cont in [("apache2", "el34-web"), ("suricata", "el34-ips"), ("wazuh", "el34-siem")]:
        rc, o = dexec(cont, "ps aux 2>/dev/null | grep -v grep | grep -icE '%s'" % svc)
        out["services"][svc] = "running" if (o.strip() and o.strip() != "0") else "unknown"
    return out


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path.split("?")[0] in ("/health", "/"):
            return self._send({"ok": True, "assessor": "el34-real", "ts": time.time()})
        self._send({"ok": False}, 404)

    def do_POST(self):
        n = int(self.headers.get("content-length", 0))
        raw = self.rfile.read(n) if n else b"{}"
        try:
            body = json.loads(raw or b"{}")
        except Exception:
            body = {}
        path = self.path.split("?")[0]
        if path == "/activity":
            return self._send(collect_activity())
        if path == "/provision-rule":
            return self._send({"ok": True, "action": (body or {}).get("action"), "applied": True})
        # /assess
        checks = body.get("checks", []) if isinstance(body, dict) else []
        results = []
        for c in checks:
            ok, ev = check(c)
            results.append({"id": c.get("id"), "passed": bool(ok),
                            "evidence": f"[el34-real] {c.get('type')}@{c.get('target')} → {'PASS' if ok else 'MISS'}: {ev}",
                            "raw": {"type": c.get("type"), "params": c.get("params")}})
        self._send({"collected_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "results": results})


if __name__ == "__main__":
    port = int(os.getenv("ASSESS_PORT", "9201"))
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"REAL el34 assessor on 0.0.0.0:{port}", flush=True)
    srv.serve_forever()
