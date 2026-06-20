#!/usr/bin/env python3
"""wazuh_probe — 실습(lab) 활동 감지 PoC. el34 Wazuh(el34-siem)에서 alert 텔레메트리를 끌어온다.

배경: tw2 의 training(실습)은 stateless 라 tw2 에 세션/이벤트를 안 남기고, 시나리오 채점
브리지였던 Assessor(:9201)는 이 el34 빌드에 부재 → tw2 는 실습 활동을 못 본다. 반면 el34
Wazuh 는 ips/web 에이전트로 실제 활동을 적재 중. 이 프로브는 그 간극을 메우는 검수용 다리다.

⚠ el34 컨테이너 내부(docker exec el34-siem)에 의존 — CLAUDE.md "표면만 의존" 원칙의 예외
(검수/하니스 용도). 운영 통합 전에 el34 가 Assessor/Wazuh API 표면을 노출하는 게 정석.

읽기 전용. 자격/타깃은 .env(SIX_DEFAULT_SSH_*) + infras DB 에서 해석(하드코딩 없음)."""
from __future__ import annotations
import json, os, re, sys, collections, datetime as dt

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "apps/api"))

SSH_USER, SSH_PASS, VM_IP = "ccc", "1", "192.168.0.151"
try:
    for ln in open(os.path.join(REPO, ".env")):
        if ln.startswith("SIX_DEFAULT_SSH_USER="):
            SSH_USER = ln.split("=", 1)[1].strip()
        elif ln.startswith("SIX_DEFAULT_SSH_PASS="):
            SSH_PASS = ln.split("=", 1)[1].strip()
except Exception:  # noqa: BLE001
    pass
# el34 타깃 IP 는 infras 에서(assessor port_map 보유 = el34) 해석
try:
    import sqlite3
    from app.config import get_settings  # type: ignore
    db = re.search(r"sqlite[^/]*:/+(/.*\.sqlite3)", get_settings().database_url).group(1)
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    for ip, pm in con.execute("SELECT vm_ip, port_map FROM infras"):
        if "assessor" in (pm or ""):
            VM_IP = ip
            break
    con.close()
except Exception:  # noqa: BLE001
    pass

ALERTS = "/var/ossec/logs/alerts/alerts.json"
SIEM_CTR = os.environ.get("EL34_SIEM_CTR", "el34-siem")


def ssh_run(cmd, timeout=30):
    import paramiko
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(VM_IP, username=SSH_USER, password=SSH_PASS,
              timeout=10, banner_timeout=10, auth_timeout=10)
    try:
        _, so, se = c.exec_command(cmd, timeout=timeout)
        return so.read().decode(errors="replace"), se.read().decode(errors="replace")
    finally:
        c.close()


def collect(timeout=20):
    """el34 Wazuh alert 텔레메트리를 끌어와 구조화 dict 로 반환(재사용용 — gwanje 가 import).
    실패해도 절대 raise 안 함 → {'ok': False, 'error': ...}. 성공 → {'ok': True, ...}."""
    try:
        out, err = ssh_run(
            f"docker exec {SIEM_CTR} sh -c "
            f"'wc -l {ALERTS} 2>/dev/null; stat -c \"MTIME=%y\" {ALERTS} 2>/dev/null; "
            f"echo ===; tail -n 400 {ALERTS} 2>/dev/null'", timeout=timeout)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "target": f"{VM_IP}:{SIEM_CTR}"}
    total = mtime = None
    lines = []
    body = out.split("===", 1)
    head = body[0] if body else ""
    m = re.search(r"^(\d+)\s", head.strip())
    if m:
        total = int(m.group(1))
    m = re.search(r"MTIME=(.+)", head)
    if m:
        mtime = m.group(1).strip()
    if len(body) > 1:
        for ln in body[1].splitlines():
            ln = ln.strip()
            if ln.startswith("{"):
                try:
                    lines.append(json.loads(ln))
                except Exception:  # noqa: BLE001
                    pass
    if err and not lines:
        return {"ok": False, "error": err.strip()[:300], "target": f"{VM_IP}:{SIEM_CTR}"}
    by_agent, by_rule, by_level, times = (collections.Counter(), collections.Counter(),
                                          collections.Counter(), [])
    for a in lines:
        by_agent[(a.get("agent") or {}).get("name", "?")] += 1
        r = a.get("rule") or {}
        by_rule[r.get("description", "?")[:50]] += 1
        by_level[r.get("level", "?")] += 1
        if a.get("timestamp"):
            times.append(a["timestamp"])
    return {"ok": True, "target": f"{VM_IP}:{SIEM_CTR}", "total": total, "mtime": mtime,
            "sample": len(lines), "span": f"{min(times)} ~ {max(times)}" if times else "n/a",
            "by_agent": dict(by_agent), "by_level": {str(k): v for k, v in by_level.items()},
            "by_rule_top": by_rule.most_common(12),
            "attack_sigs": sorted({d for d in by_rule if "Suricata" in d or "Alert" in d})}


def main():
    d = collect()
    if not d.get("ok"):
        print(f"[wazuh_probe ERR @ {d.get('target')}] {d.get('error')}")
        return 1
    print(f"╔══ Wazuh 실습-활동 프로브  ({SSH_USER}@{d['target']}) ══")
    print(f"║ alerts.json: 총 {d['total']}줄, mtime={d['mtime']}")
    print(f"║ 표본(최근 {d['sample']}건) 시간범위: {d['span']}")
    print(f"║ agent별: " + ", ".join(f"{k}={v}" for k, v in d['by_agent'].items()))
    print(f"║ level별: " + ", ".join(f"L{k}={v}" for k, v in sorted(d['by_level'].items())))
    print(f"║ rule TOP5:")
    for desc, n in d['by_rule_top'][:5]:
        print(f"║   {n:>3}× {desc}")
    print("╚════")
    print("###JSON### " + json.dumps(d, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
