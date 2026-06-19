#!/usr/bin/env python3
"""tubewar 관제(control-room) 원샷 수집기.

"관제 시작" 한 번에: 스택 헬스 + 활성배틀 + 채점스트림 + 학생활동 + 그레이더/피드백
헬스 + SIEM 적재 + admin 엔드포인트 검증 + 스마트-트리거 salience 점수까지 한 방에 수집.

    .venv/bin/python scripts/monitor/gwanje.py            # 델타(직전 대비 새것만)
    .venv/bin/python scripts/monitor/gwanje.py --reset    # 커서 초기화(다음 실행이 베이스라인)
    .venv/bin/python scripts/monitor/gwanje.py --json      # 머신용 JSON 만 출력

읽기 전용. DB 는 RO 로 열고, 어떤 상태도 변경하지 않는다.
설정(.env)에서 DATABASE_URL/JWT/admin 을 자동 로드하므로 하드코딩 의존 없음.
"""
from __future__ import annotations
import json, os, re, shutil, sqlite3, subprocess, sys, datetime as dt, urllib.request

REPO = "/home/ccc/tubewar"
sys.path.insert(0, os.path.join(REPO, "apps/api"))
CURSOR = "/tmp/mon/cursor.json"
os.makedirs("/tmp/mon", exist_ok=True)

ARGV = sys.argv[1:]


def _opt(name, default=None):
    if name in ARGV:
        i = ARGV.index(name)
        if i + 1 < len(ARGV):
            return ARGV[i + 1]
    return default


JSON_ONLY = "--json" in ARGV
LIST_AGENTS = "--agents" in ARGV
AGENT = _opt("--agent", "deterministic")
MODEL = _opt("--model")
ALLOW_BILLED = "--allow-billed" in ARGV
if "--reset" in ARGV and os.path.exists(CURSOR):
    os.remove(CURSOR)

# ── 설정 로드(.env) ─────────────────────────────────────────────
DB_PATH = os.path.join(REPO, ".data/tubewar.sqlite3")
JWT_SECRET = None
ADMIN_EMAIL = "admin@tubewar.app"
API = "http://127.0.0.1:9200"
OS_URL = "http://127.0.0.1:9201"
LLM_BASE_URL = "http://127.0.0.1:11434"
LLM_MODEL_DEFAULT = "gemma3:4b"
try:
    from app.config import get_settings  # type: ignore

    s = get_settings()
    JWT_SECRET = s.jwt_secret
    ADMIN_EMAIL = s.admin_email
    API = f"http://127.0.0.1:{s.api_port}"
    LLM_BASE_URL = s.llm_base_url
    LLM_MODEL_DEFAULT = s.llm_model
    m = re.search(r"sqlite[^/]*:/+(/.*\.sqlite3)", s.database_url)
    if m:
        DB_PATH = m.group(1)
except Exception:  # noqa: BLE001  (system python fallback — token 기능만 빠짐)
    pass
# .env 에서 OPENSEARCH_URL 직접 파싱(systemd 가 .env 를 API 프로세스에만 주입하므로)
try:
    for ln in open(os.path.join(REPO, ".env")):
        if ln.startswith("OPENSEARCH_URL="):
            OS_URL = ln.split("=", 1)[1].strip().strip('"').strip("'")
except Exception:  # noqa: BLE001
    pass


# ── 관제 에이전트 레지스트리(요금 나오는 API 는 기본 차단) ──────────
AGENTS = {
    "deterministic": {"cost": "free", "desc": "규칙기반 salience/health (LLM 없음·기본값)"},
    "local": {"cost": "free", "desc": "로컬 ollama 요약(자가호스팅·무과금)"},
    "claude": {"cost": "BILLED", "desc": "claude -p (과금 가능 → 기본 차단)"},
}


def ollama_up():
    _, d = http_json(LLM_BASE_URL + "/api/tags", timeout=3)
    return isinstance(d, dict) and "models" in d


def _brief(snap):
    return {
        "ts": snap["ts_kst"], "salience": snap["salience"], "why": snap["salience_why"],
        "active": [{"id": b.get("id"), "scen": b.get("scenario_id"), "cohort": b.get("cohort_id")}
                   for b in snap["active_battles"] if isinstance(b, dict) and "id" in b],
        "orphans": snap["orphans"], "stack": snap["stack"],
        "new_events": snap["new_events_count"], "activity": snap["activity_new_total"],
        "stuck_pending": snap["stuck_pending"],
        "journal_warn": {k: snap["journal"].get(k) for k in
                         ("assess_bad", "bulk_bad", "timeouts", "errors", "grade_fail")},
    }


def ai_summarize(snap, agent, model):
    """선택된 에이전트로 자연어 요약(선택). 과금 API 는 기본 차단."""
    if agent == "deterministic":
        return None
    if agent == "local":
        model = model or LLM_MODEL_DEFAULT
        if not LLM_BASE_URL.startswith(("http://127.0.0.1", "http://localhost")):
            return f"[차단] local 에이전트는 localhost 엔드포인트만 허용(현재 {LLM_BASE_URL})."
        prompt = ("다음 tubewar 학생활동 관제 스냅샷을 한국어 3~4줄로 요약. "
                  "이상징후(고아배틀·cohort_id NULL·채점적체·로그오류) 우선:\n"
                  + json.dumps(_brief(snap), ensure_ascii=False))
        body = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode()
        req = urllib.request.Request(LLM_BASE_URL + "/api/generate", data=body, method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                return f"[local:{model}] " + json.load(r).get("response", "").strip()
        except Exception as e:  # noqa: BLE001
            return (f"[local 에이전트 실패: {type(e).__name__} — ollama 미가동? "
                    f"'ollama serve && ollama pull {model}' 후 재시도]")
    if agent == "claude":
        if not ALLOW_BILLED:
            return ("[차단] claude 에이전트는 과금 가능 API → 정책상 기본 차단. "
                    "무료 대안: --agent deterministic(기본) | --agent local. "
                    "정말 필요하면 --allow-billed 명시.")
        model = model or "claude-haiku-4-5"
        prompt = ("tubewar 관제 스냅샷을 한국어 3~4줄로 요약(이상징후 우선):\n"
                  + json.dumps(_brief(snap), ensure_ascii=False))
        try:
            r = subprocess.run(["claude", "-p", "--model", model, prompt],
                               capture_output=True, text=True, timeout=120)
            return f"[claude:{model}] " + (r.stdout or r.stderr).strip()
        except Exception as e:  # noqa: BLE001
            return f"[claude 에이전트 실패: {e}]"
    return f"[알 수 없는 에이전트: {agent} — --agents 로 목록 확인]"


def http_json(url, token=None, timeout=8, method="GET"):
    req = urllib.request.Request(url, method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:  # noqa
        return e.code, None
    except Exception as e:  # noqa: BLE001
        return None, {"_error": f"{type(e).__name__}: {e}"}


def mint_token():
    if not JWT_SECRET:
        return None
    try:
        from jose import jwt  # type: ignore

        con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        row = con.execute(
            "SELECT id,email,role FROM users WHERE role='admin' ORDER BY id LIMIT 1"
        ).fetchone()
        con.close()
        if not row:
            return None
        now = dt.datetime.now(dt.timezone.utc)
        payload = {"sub": str(row[0]), "email": row[1], "role": row[2],
                   "iat": int(now.timestamp()),
                   "exp": int((now + dt.timedelta(hours=12)).timestamp())}
        return jwt.encode(payload, JWT_SECRET, algorithm="HS256")
    except Exception:  # noqa: BLE001
        return None


def q(con, sql, args=()):
    try:
        cur = con.execute(sql, args)
        cols = [c[0] for c in cur.description] if cur.description else []
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    except Exception as e:  # noqa: BLE001
        return [{"_error": f"{type(e).__name__}: {e}"}]


def scalar(con, sql, args=()):
    try:
        r = con.execute(sql, args).fetchone()
        return r[0] if r else None
    except Exception:  # noqa: BLE001
        return None


def load_cursor():
    try:
        return json.load(open(CURSOR))
    except Exception:  # noqa: BLE001
        return {}


def os_indices():
    st, data = http_json(OS_URL + "/_cat/indices/tubewar-*?format=json&h=index,docs.count")
    if isinstance(data, list):
        return {d["index"]: int(d.get("docs.count") or 0) for d in data}
    return {"_disabled": "중앙 OpenSearch 비활성(tw2: TUBEWAR_LAB_MONITOR=0 — SIEM은 el34 Wazuh 사용)"}


def systemd_status():
    out = {}
    for svc in ("tw2-api", "tw2-ui"):
        try:
            r = subprocess.run(["systemctl", "is-active", svc],
                               capture_output=True, text=True, timeout=6)
            out[svc] = r.stdout.strip() or r.stderr.strip()
        except Exception as e:  # noqa: BLE001
            out[svc] = f"err:{e}"
    return out


def journal_health(since):
    try:
        out = subprocess.run(
            ["journalctl", "-u", "tubewar-api", "--since", since, "--no-pager", "-o", "cat"],
            capture_output=True, text=True, timeout=15).stdout
    except Exception as e:  # noqa: BLE001
        return {"_error": str(e)}
    lines = out.splitlines()
    err, timeouts, a_ok, a_bad, b_ok, b_bad, gfail = [], 0, 0, 0, 0, 0, []
    for ln in lines:
        low = ln.lower()
        if "/assess" in ln and "200 OK" in ln:
            a_ok += 1
        elif "/assess" in ln and ("HTTP/1.1 4" in ln or "HTTP/1.1 5" in ln):
            a_bad += 1
        if "_bulk" in ln and "200 OK" in ln:
            b_ok += 1
        elif "_bulk" in ln and ("HTTP/1.1 4" in ln or "HTTP/1.1 5" in ln):
            b_bad += 1
        if "readtimeout" in low or "read timeout" in low or "timed out" in low:
            timeouts += 1
        if "grade_submission" in low and "fail" in low:
            gfail.append(ln[-160:])
        if (("traceback" in low or "exception" in low or " error " in low
             or "critical" in low) and "http request" not in low):
            err.append(ln[-200:])
    return {"lines": len(lines), "errors": err[-10:], "timeouts": timeouts,
            "assess_ok": a_ok, "assess_bad": a_bad, "bulk_ok": b_ok,
            "bulk_bad": b_bad, "grade_fail": gfail[-5:]}


def main():
    if LIST_AGENTS:
        print("사용 가능한 관제 에이전트 (--agent <name> [--model <m>]):")
        for k, v in AGENTS.items():
            extra = ""
            if k == "local":
                extra = "  [가동중]" if ollama_up() else f"  [미가동: 'ollama serve' 필요·기본 {LLM_MODEL_DEFAULT}]"
            if k == "claude":
                extra = ("  [CLI있음]" if shutil.which("claude") else "  [CLI없음]") + " · 기본 차단(--allow-billed)"
            print(f"  {k:14} cost={v['cost']:6} {v['desc']}{extra}")
        return
    cur = load_cursor()
    token = mint_token()
    now = dt.datetime.now(dt.timezone.utc)
    kst = (now + dt.timedelta(hours=9)).replace(tzinfo=None)  # naive: heartbeat 뺄셈용
    le, la = cur.get("last_event_id", 0), cur.get("last_activity_id", 0)
    ls, lf = cur.get("last_submission_id", 0), cur.get("last_feedback_id", 0)
    baseline = not cur
    flagged = set(cur.get("flagged_orphans", []))

    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)

    active = q(con, "SELECT id,scenario_id,cohort_id,mode,status,monitor,started_at,"
                    "time_limit_sec,created_by FROM battles WHERE status='active' ORDER BY id")
    recent_done = q(con, "SELECT id,scenario_id,cohort_id,mode,status,ended_at FROM battles "
                         "WHERE status IN('completed','cancelled') ORDER BY id DESC LIMIT 5")
    new_events = q(con, "SELECT id,battle_id,actor_user_id,event_type,target,points,ts,"
                        "substr(COALESCE(detail,''),1,800) detail FROM battle_events "
                        "WHERE id>? ORDER BY id LIMIT 80", (le,))
    new_act_total = scalar(con, "SELECT COUNT(*) FROM activity_events WHERE id>?", (la,)) or 0
    act_kind = q(con, "SELECT kind,COUNT(*) n FROM activity_events WHERE id>? GROUP BY kind "
                      "ORDER BY n DESC", (la,))
    act_student = q(con, "SELECT user_id,COUNT(*) n FROM activity_events WHERE id>? "
                         "GROUP BY user_id ORDER BY n DESC LIMIT 8", (la,))
    sub_status = q(con, "SELECT grade_status,COUNT(*) n FROM student_submissions "
                        "GROUP BY grade_status", ())
    new_subs = q(con, "SELECT id,user_id,scenario_id,verdict,awarded_points,grade_status "
                      "FROM student_submissions WHERE id>? ORDER BY id LIMIT 50", (ls,))
    stuck = q(con, "SELECT COUNT(*) n FROM student_submissions WHERE grade_status='pending'", ())
    fail_sig_rows = q(con, "SELECT DISTINCT scenario_id, mission_side, mission_order "
                           "FROM student_submissions WHERE verdict='fail'", ())
    fail_sigs = sorted({f"{r.get('scenario_id')}/{r.get('mission_side')}/{r.get('mission_order')}"
                        for r in fail_sig_rows if isinstance(r, dict) and "scenario_id" in r})
    new_fb = q(con, "SELECT id,user_id,battle_id,model,cost_usd,length(content_md) clen "
                    "FROM student_feedback WHERE id>? ORDER BY id LIMIT 20", (lf,))
    prog = []
    for b in active:
        if isinstance(b, dict) and "id" in b:
            prog.append({"battle_id": b["id"], "rows": q(
                con, "SELECT user_id,completion,steps_done,steps_total,bottleneck_flags "
                     "FROM progress_snapshots WHERE battle_id=? ORDER BY id DESC LIMIT 6",
                (b["id"],))})

    mx = lambda t: scalar(con, f"SELECT MAX(id) FROM {t}")  # noqa: E731
    max_ev = mx("battle_events") or le
    max_act = mx("activity_events") or la
    max_sub = mx("student_submissions") or ls
    max_fb = mx("student_feedback") or lf
    con.close()

    idx = os_indices()
    prev_idx = cur.get("siem", {})
    idx_delta = {k: {"now": v, "delta": v - prev_idx.get(k, 0)}
                 for k, v in (idx.items() if "_error" not in idx else [])
                 if (v - prev_idx.get(k, 0)) != 0}

    since = cur.get("last_run_kst") or (kst - dt.timedelta(minutes=8)).strftime("%Y-%m-%d %H:%M:%S")
    jl = journal_health(since)
    svc = systemd_status()
    api_st, api_h = http_json(API + "/health")

    # ── 고아 배틀 탐지(active > 6h) + admin 엔드포인트 검증 ──
    orphans, new_orphans = [], []
    for b in active:
        if not (isinstance(b, dict) and b.get("started_at")):
            continue
        try:
            st = dt.datetime.fromisoformat(str(b["started_at"]))
            age_h = (now.replace(tzinfo=None) - st).total_seconds() / 3600
        except Exception:  # noqa: BLE001
            age_h = 0
        if age_h > 6:
            orphans.append({"battle_id": b["id"], "age_h": round(age_h, 1)})
            if b["id"] not in flagged:
                new_orphans.append(b["id"])
    probe = {}
    if token:
        for b in active:
            if isinstance(b, dict) and "id" in b:
                stt, pj = http_json(f"{API}/monitoring/battles/{b['id']}/progress", token)
                probe[b["id"]] = {"http": stt, "ok": stt == 200}

    # ── 스마트 트리거 salience 점수 ──
    sal, why = 0, []

    def add(pts, label):
        nonlocal sal
        if pts:
            sal += pts
            why.append(f"+{pts} {label}")

    if not baseline:
        graded_new = [e for e in new_events if isinstance(e, dict)
                      and re.search(r"verdict|awarded|grading", e.get("detail") or "")]
        fails = [e for e in graded_new if re.search(r"fail|partial|review", e.get("detail") or "")]
        add(min(len(graded_new), 6), f"새 채점이벤트 {len(graded_new)}")
        add(min(len(fails), 3), f"partial/fail {len(fails)}(true-fail은 verdict확인)")
        add(min(len(new_fb) * 1, 3), f"새 AI피드백 {len(new_fb)}")
        add(min(new_act_total // 80, 2), f"학생활동 {new_act_total}")  # 노이즈(고아폴링) 완화
    cur_active_ids = [b["id"] for b in active if isinstance(b, dict) and "id" in b]
    new_active = [bid for bid in cur_active_ids if bid not in cur.get("seen_active", [])]
    ended = [bid for bid in cur.get("seen_active", []) if bid not in cur_active_ids]
    done_ids = [b.get("id") for b in recent_done if isinstance(b, dict) and "id" in b]
    # 검수 캠페인은 미션마다 새 배틀을 열어 동일 시나리오가 반복됨 → 배틀 churn 은 약신호.
    add(min(len(new_active), 2) * (not baseline), f"새 배틀 churn {new_active}")
    add(min(len(ended), 2) * (not baseline), f"배틀 종료 {ended}")
    # 진짜 보고가치 = 새 '시나리오' 등장(주차/트랙 전환). 활성+최근완료에서 미관측 scen.
    scen_now = sorted({b.get("scenario_id") for b in (active + recent_done)
                       if isinstance(b, dict) and b.get("scenario_id") is not None})
    new_scen = [s for s in scen_now if s not in cur.get("seen_scenarios", [])]
    add(5 * bool(new_scen and not baseline), f"⚠새 시나리오 {new_scen}")
    # 신규 'fail 유형'(scen/side/order) — 이미 본 fail 시그니처는 무시, 처음 보는 fail 만 강신호
    new_fail_sigs = [s for s in fail_sigs if s not in cur.get("seen_fail_sigs", [])]
    add(5 * bool(new_fail_sigs and not baseline), f"⚠신규 fail유형 {new_fail_sigs}")
    sp = stuck[0].get("n", 0) if stuck and isinstance(stuck[0], dict) else 0
    add(4 * (sp > 3), f"채점대기 적체 {sp}")
    add(5 * bool(jl.get("grade_fail")), "그레이더 실패로그")
    add(min(len(jl.get("errors", [])) * 2, 6), f"로그오류 {len(jl.get('errors', []))}")
    add(3 * bool(jl.get("assess_bad") or jl.get("bulk_bad")), "assess/bulk 실패")
    add(4 * bool(new_orphans), f"신규 고아배틀 {new_orphans}")
    add(3 * any(v != "active" for v in svc.values()), "서비스 비정상")
    add(4 * (api_st != 200), "API 헬스 실패")

    heartbeat_min = 25
    last_report = cur.get("last_report_kst")
    hb_due = True
    if last_report:
        try:
            elapsed = (kst - dt.datetime.fromisoformat(last_report)).total_seconds() / 60
            hb_due = elapsed >= heartbeat_min
        except Exception:  # noqa: BLE001
            hb_due = True
    should_report = baseline or sal >= 5 or hb_due

    snap = {"ts_kst": kst.strftime("%Y-%m-%d %H:%M:%S"), "baseline": baseline,
            "stack": {"api_health": api_st, "services": svc, "opensearch": ("_error" not in idx and "_disabled" not in idx)},
            "active_battles": active, "orphans": orphans, "recent_done": recent_done,
            "new_events_count": len(new_events), "new_events": new_events,
            "activity_new_total": new_act_total, "activity_by_kind": act_kind,
            "activity_by_student": act_student, "submission_status": sub_status,
            "stuck_pending": sp, "new_submissions": new_subs, "new_feedback": new_fb,
            "progress": prog, "admin_probe": probe, "siem_delta": idx_delta, "siem_total": idx,
            "journal": jl, "salience": sal, "salience_why": why,
            "heartbeat_due": hb_due, "should_report": should_report}

    # 커서 저장
    json.dump({"last_event_id": max_ev, "last_activity_id": max_act,
               "last_submission_id": max_sub, "last_feedback_id": max_fb,
               "last_run_kst": kst.strftime("%Y-%m-%d %H:%M:%S"),
               "last_report_kst": kst.strftime("%Y-%m-%d %H:%M:%S") if should_report else last_report,
               "seen_active": [b["id"] for b in active if isinstance(b, dict) and "id" in b],
               "seen_done": sorted(set(list(cur.get("seen_done", [])) + done_ids))[-60:],
               "seen_scenarios": sorted(set(list(cur.get("seen_scenarios", [])) + scen_now)),
               "seen_fail_sigs": fail_sigs,
               "flagged_orphans": sorted(set(list(flagged) + [o["battle_id"] for o in orphans])),
               "siem": idx if "_error" not in idx else prev_idx},
              open(CURSOR, "w"), ensure_ascii=False)

    ai = ai_summarize(snap, AGENT, MODEL)
    snap["agent"] = AGENT
    snap["ai_summary"] = ai

    if JSON_ONLY:
        print(json.dumps(snap, ensure_ascii=False, default=str))
        return

    P = print
    bad_svc = [k for k, v in svc.items() if v != "active"]
    P(f"╔══ 관제 {snap['ts_kst']} KST {'[BASELINE]' if baseline else ''} ══")
    P(f"║ 스택: API={api_st} {'OK' if api_st==200 else '⚠'} | svc {'all-active' if not bad_svc else '⚠'+str(bad_svc)} | SIEM(중앙OS)={'OK' if ('_error' not in idx and '_disabled' not in idx) else ('비활성' if '_disabled' in idx else '⚠DOWN')}")
    P(f"║ 활성배틀 {len(active)} | 새채점이벤트 {len(new_events)} | 새활동 {new_act_total} | 새피드백 {len(new_fb)} | 채점대기 {sp}")
    for b in active:
        if isinstance(b, dict) and "id" in b:
            co = b.get("cohort_id")
            f = "" if co else "  ⚠cohort_id=NULL→코호트SIEM 미적재"
            pr = probe.get(b["id"], {})
            P(f"║  ▶#{b['id']} scen={b.get('scenario_id')} {b.get('mode')}/{b.get('monitor')} "
              f"cohort={co} since={b.get('started_at')}{f}"
              + (f"  progress_api={pr.get('http')}" if pr else ""))
    if orphans:
        P(f"║  ⚠고아배틀(active>6h): " + ", ".join(f"#{o['battle_id']}({o['age_h']}h)" for o in orphans))
    if sub_status:
        P("║ 제출상태: " + ", ".join(f"{r.get('grade_status')}={r.get('n')}"
                                  for r in sub_status if "grade_status" in r))
    j = jl
    warn = j.get("errors") or j.get("grade_fail") or j.get("assess_bad") or j.get("timeouts") or j.get("bulk_bad")
    P(f"║ 로그({j.get('lines')}줄): assess {j.get('assess_ok')}ok/{j.get('assess_bad')}bad "
      f"| bulk {j.get('bulk_ok')}ok/{j.get('bulk_bad')}bad | timeout {j.get('timeouts')} "
      f"| gradeFail {len(j.get('grade_fail', []))} | err {len(j.get('errors', []))} {'⚠' if warn else 'OK'}")
    if idx_delta:
        P("║ SIEM 변화: " + ", ".join(f"{k.replace('tubewar-activity-','')}{'+' if v['delta']>0 else ''}{v['delta']}"
                                    for k, v in idx_delta.items()))
    P(f"║ ▶ salience={sal}  ({'; '.join(why) if why else '변화 없음'})")
    P(f"║ ▶ should_report={should_report}  (heartbeat_due={hb_due}, threshold=5)")
    P(f"║ ▶ agent={AGENT} cost={AGENTS.get(AGENT, {}).get('cost', '?')}"
      + (f" model={MODEL}" if MODEL else ""))
    if ai:
        P("║ ▶ AI요약: " + ai.replace("\n", " "))
    P("╚════")
    if not JSON_ONLY:
        print("###JSON### " + json.dumps(snap, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
