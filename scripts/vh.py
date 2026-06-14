#!/usr/bin/env python3
"""검수 하니스 라이브러리 (verify harness).

운영 tubewar API(9200)를 실 사용자 JWT로 구동하고, 6v6 호스트에 docker exec 로
실제 공격/방어 증거를 심어 claude 라이브 채점을 거치게 하는 1차 도구 모음.

병렬 금지·자동 일괄 금지: 이 모듈은 "한 미션을 사람처럼 수행"하기 위한 primitive 만 제공.
실제 미션 내용(무슨 공격/방어를 하고 무슨 보고를 할지)은 호출자가 시나리오를 읽고 결정한다.

사용:
  from scripts import vh   # 또는 python -c "import sys;sys.path.insert(0,'scripts');import vh"
"""
import os, sys, time, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = os.environ.get("VH_API", "http://127.0.0.1:9200")

# ---- .env 로드 + app import (issue_token 용) ----
def _load_env():
    envp = ROOT / ".env"
    for line in envp.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k, v)

_load_env()
sys.path.insert(0, str(ROOT / "apps" / "api"))

import httpx
import paramiko

# 호스트 자격 (사용자 제공): 6v6 머신 직접 SSH
HOST_USER = os.environ.get("VH_HOST_USER", "ccc")
HOST_PASS = os.environ.get("VH_HOST_PASS", "1")

# infra_id -> (vm_ip, needs_sudo_for_docker)
INFRA_HOST = {}

def _refresh_infra_hosts():
    import sqlite3, re
    dburl = os.environ["DATABASE_URL"]
    path = re.sub(r"^sqlite\+aiosqlite:/+", "/", dburl)
    c = sqlite3.connect(path)
    for iid, ip in c.execute("SELECT id, vm_ip FROM infras"):
        INFRA_HOST[iid] = ip
    c.close()
    return dict(INFRA_HOST)

# ---------------- 토큰 ----------------
_TOKENS = {}
def tokens():
    """{email: jwt} 발급 (issue_token, 서버 .env 시크릿과 동일)."""
    global _TOKENS
    if _TOKENS:
        return _TOKENS
    import asyncio, sqlite3, re
    from app.security import issue_token
    from app.models import User
    dburl = os.environ["DATABASE_URL"]
    path = re.sub(r"^sqlite\+aiosqlite:/+", "/", dburl)
    c = sqlite3.connect(path)
    out = {}
    for uid, email, role in c.execute("SELECT id,email,role FROM users"):
        u = User(); u.id = uid; u.email = email; u.role = role
        out[email] = issue_token(u)
    c.close()
    _TOKENS = out
    return out

def tok(email):
    return tokens()[email]

# ---------------- API ----------------
def api(method, path, token=None, body=None, timeout=30.0):
    h = {"content-type": "application/json"}
    if token:
        h["authorization"] = "Bearer " + token
    r = httpx.request(method, API + path, headers=h,
                      json=body, timeout=timeout)
    try:
        data = r.json()
    except Exception:
        data = r.text
    return r.status_code, data

# ---------------- 호스트 exec ----------------
_SSH = {}
def _ssh(ip):
    if ip not in _SSH:
        cli = paramiko.SSHClient()
        cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        cli.connect(ip, username=HOST_USER, password=HOST_PASS, timeout=10,
                    banner_timeout=10, auth_timeout=10)
        _SSH[ip] = cli
    return _SSH[ip]

def host_exec(ip, cmd, sudo=None, timeout=120):
    """6v6 호스트에서 셸 실행. sudo=None이면 docker 그룹 여부 자동 판단(.78만 sudo)."""
    cli = _ssh(ip)
    if sudo is None:
        # ccc가 docker 그룹이 아니면 sudo 필요. 간단히 ip로 판단(.78=sudo) — 일반화는 그룹조회.
        sudo = ip.endswith(".78")
    full = f"echo {HOST_PASS} | sudo -S bash -lc {json.dumps(cmd)}" if sudo else f"bash -lc {json.dumps(cmd)}"
    i, o, e = cli.exec_command(full, timeout=timeout)
    out = o.read().decode(errors="replace")
    err = e.read().decode(errors="replace")
    rc = o.channel.recv_exit_status()
    return rc, out, err

def docker_exec(ip, container, cmd, timeout=120):
    """6v6-<container> 안에서 명령 실행."""
    return host_exec(ip, f"docker exec {container} sh -lc {json.dumps(cmd)}", timeout=timeout)

# ---------------- 배틀 lifecycle ----------------
def create_solo(scenario_id, user_email, infra_id, monitor="claude", target_apps=None, cohort_id=None):
    uid = _uid(user_email)
    body = {"scenario_id": scenario_id, "mode": "solo", "monitor": monitor,
            "target_apps": target_apps or [], "hint_enabled": False,
            "participants": [{"user_id": uid, "role": "solo", "infra_id": infra_id}]}
    if cohort_id: body["cohort_id"] = cohort_id
    return api("POST", "/battles", tok(user_email), body)

def create_duel(scenario_id, red_email, red_infra, blue_email, blue_infra,
                monitor="claude", target_apps=None, cohort_id=None):
    """admin 이 lobby 생성 후 양측 join."""
    adm = _admin_email()
    body = {"scenario_id": scenario_id, "mode": "duel", "monitor": monitor,
            "target_apps": target_apps or [], "hint_enabled": False, "participants": []}
    if cohort_id: body["cohort_id"] = cohort_id
    st, d = api("POST", "/battles", tok(adm), body)
    if st >= 300: return st, d
    bid = d["battle"]["id"]
    api("POST", f"/battles/{bid}/join", tok(red_email),
        {"role": "red", "infra_id": red_infra})
    api("POST", f"/battles/{bid}/join", tok(blue_email),
        {"role": "blue", "infra_id": blue_infra})
    return st, d

def start(bid, email):
    return api("POST", f"/battles/{bid}/start", tok(email))

def submit(bid, email, *, side, order, event_type, target, what_i_did, what_happened,
           description="", points=0):
    return api("POST", f"/battles/{bid}/events", tok(email), {
        "event_type": event_type, "target": target, "description": description,
        "points": points, "mission_order": order, "mission_side": side,
        "what_i_did": what_i_did, "what_happened": what_happened,
        "client_token": f"vh-{bid}-{side}-{order}-{int(time.time())}",
    }, timeout=60)

def wait_grade(submission_id, email, timeout=600, poll=6):
    """제출 채점 완료까지 폴링. (grade_status: pending->graded/failed)"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        st, subs = api("GET", "/me/submissions", tok(email))
        if st < 300 and isinstance(subs, list):
            for s in subs:
                if s.get("id") == submission_id:
                    if s.get("grade_status") in ("graded", "failed"):
                        return s
        time.sleep(poll)
    return None

def end(bid, email):
    return api("POST", f"/battles/{bid}/end", tok(email))

# ---------------- helpers ----------------
def _uid(email):
    import sqlite3, re
    path = re.sub(r"^sqlite\+aiosqlite:/+", "/", os.environ["DATABASE_URL"])
    c = sqlite3.connect(path)
    r = c.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
    c.close()
    return r[0] if r else None

def _admin_email():
    import sqlite3, re
    path = re.sub(r"^sqlite\+aiosqlite:/+", "/", os.environ["DATABASE_URL"])
    c = sqlite3.connect(path)
    r = c.execute("SELECT email FROM users WHERE role='admin' LIMIT 1").fetchone()
    c.close()
    return r[0]

_SCN_MAP = {}
def scenario_int_id(string_id):
    """YAML 문자열 id(soc-adv-w01) → DB 정수 id. 제목 일치로 매핑(캐시)."""
    global _SCN_MAP
    if not _SCN_MAP:
        import glob, os.path as osp, yaml
        st, scns = api("GET", "/scenarios", tok(_admin_email()))
        by_title = {s.get("title"): s.get("id") for s in scns}
        for p in glob.glob(str(ROOT / "contents" / "battle-scenarios" / "*.yaml")):
            try:
                d = yaml.safe_load(open(p))
            except Exception:
                continue
            if isinstance(d, dict) and d.get("title") in by_title:
                _SCN_MAP[osp.splitext(osp.basename(p))[0]] = by_title[d["title"]]
    return _SCN_MAP.get(string_id)

if __name__ == "__main__":
    # 배선 점검
    print("infra hosts:", _refresh_infra_hosts())
    tks = tokens(); print("tokens for:", list(tks))
    st, scns = api("GET", "/scenarios", tok(_admin_email()))
    print("GET /scenarios:", st, "count=", len(scns) if isinstance(scns, list) else scns)
