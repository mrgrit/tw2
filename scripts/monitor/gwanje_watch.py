#!/usr/bin/env python3
"""gwanje_watch — 관제 트리거 게이트(싼 폴링 + 비싼 분석 분리).

설계(이니셔티브 #2 §5): **클럭은 *무료 탐침*을 돌리고, *비싼 추론(LLM 에이전트)*은
salience 가 부를 때만 깨운다.** cron/loop 가 이 스크립트를 짧은 주기로 호출한다(전부 무료).
한 호출 = gwanje 1회(델타) + 2계층 트리거 판정:

  • 사이클-tier  : gwanje 의 should_report(salience≥5 | heartbeat | baseline).  → "요약 해설" 시점.
  • 보고서-tier  : 시간이 아닌 *에피소드 경계* 누산 —
                   severity(Assessor 신규 다운·grade_fail·API down) 즉시 |
                   phase완료(배틀 신규 completed) | 누적(주목 사이클 ≥N) | 유휴마감(활성→유휴 지속).

출력: 한 줄 결정(+escalate 사유). 상태는 /tmp/mon/watch.json, 결정 트레일은 watch.jsonl.
종료코드: 0=침묵, 10=사이클 보고, 20=보고서 작성 권장(사이클 포함). cron 이 코드로 분기 가능.

    .venv/bin/python scripts/monitor/gwanje_watch.py            # 1회 게이트 판정
    .venv/bin/python scripts/monitor/gwanje_watch.py --reset    # 누산 상태 초기화
    watch -n300 '.../gwanje_watch.py'                          # 5분 폴링(무료). 코드 20 이면 사람/에이전트 호출.
"""
from __future__ import annotations
import json, os, subprocess, sys, datetime as dt

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GWANJE = os.path.join(REPO, "scripts/monitor/gwanje.py")
STATE = "/tmp/mon/watch.json"
TRAIL = "/tmp/mon/watch.jsonl"
os.makedirs("/tmp/mon", exist_ok=True)

ACCUM_CYCLES = int(os.environ.get("GWANJE_REPORT_CYCLES", "6"))  # 주목 사이클 N건 누적 시 보고
IDLE_WRAP_CYCLES = int(os.environ.get("GWANJE_IDLE_WRAP", "3"))   # 활성→유휴 N사이클 지속 시 마감보고


def run_gwanje():
    """gwanje 를 현재 인터프리터로 1회 실행하고 JSON 스냅샷을 돌려준다(무료·deterministic)."""
    r = subprocess.run([sys.executable, GWANJE, "--json"],
                       capture_output=True, text=True, timeout=60)
    line = ""
    for ln in (r.stdout or "").splitlines():
        if ln.startswith("###JSON###"):
            line = ln[len("###JSON###"):].strip()
        elif ln.strip().startswith("{") and '"salience"' in ln:
            line = ln.strip()
    if not line:
        raise RuntimeError(f"gwanje JSON 미발견 (stderr: {(r.stderr or '')[-300:]})")
    return json.loads(line)


def load(path, default):
    try:
        return json.load(open(path))
    except Exception:  # noqa: BLE001
        return default


def main():
    if "--reset" in sys.argv:
        for p in (STATE, TRAIL):
            if os.path.exists(p):
                os.remove(p)
        print("watch 상태 초기화")
        return 0

    st = load(STATE, {})
    snap = run_gwanje()
    sal = snap.get("salience", 0)
    why = snap.get("salience_why", [])
    cycle_report = bool(snap.get("should_report"))

    # ── 보고서-tier 트리거 누산 ──────────────────────────────
    reasons = []  # 보고서 작성 사유

    # (1) severity — 즉시 보고할 강신호
    assessor = (snap.get("stack") or {}).get("assessor") or {}
    assessor_down = isinstance(assessor, dict) and any(v is False for v in assessor.values())
    prev_assessor_down = st.get("assessor_down", False)
    if assessor_down and not prev_assessor_down:
        reasons.append("Assessor 신규 다운(라이브 모니터 불능)")
    if assessor_down is False and prev_assessor_down:
        reasons.append("Assessor 복구")
    jl = snap.get("journal") or {}
    if jl.get("grade_fail"):
        reasons.append(f"그레이더 실패로그 {len(jl['grade_fail'])}")
    if snap.get("stack", {}).get("api_health") not in (200, None):
        reasons.append("API 헬스 실패")

    # (2) phase 완료 — 배틀이 신규로 completed/cancelled 됐는가
    done_now = sorted({b.get("id") for b in (snap.get("recent_done") or [])
                       if isinstance(b, dict) and b.get("id") is not None})
    new_done = [d for d in done_now if d not in st.get("seen_done", [])]
    if new_done:
        reasons.append(f"phase완료: 배틀 {new_done} 종료")

    # (3) 누적 — 마지막 보고 후 주목 사이클 N건
    cycles_accum = st.get("cycles_accum", 0) + (1 if cycle_report else 0)
    if cycles_accum >= ACCUM_CYCLES:
        reasons.append(f"누적 주목 사이클 {cycles_accum}≥{ACCUM_CYCLES}")

    # (4) 유휴 마감 — 활성배틀 있었다가 지속 유휴
    active_n = len([b for b in (snap.get("active_battles") or []) if isinstance(b, dict)])
    orphan_ids = {o.get("battle_id") for o in (snap.get("orphans") or [])}
    live_n = len([b for b in (snap.get("active_battles") or [])
                  if isinstance(b, dict) and b.get("id") not in orphan_ids])  # 좀비 제외 진짜 활성
    idle = live_n == 0
    idle_streak = st.get("idle_streak", 0) + 1 if idle else 0
    was_active = st.get("ever_active", False)
    if was_active and idle and idle_streak == IDLE_WRAP_CYCLES:  # 마감은 한 번만
        reasons.append(f"유휴 마감(활성→유휴 {idle_streak}사이클)")

    report_tier = bool(reasons)

    # ── edge vs level: 지속되는 *동일* 조건은 매 사이클 재경보하지 않고 heartbeat 주기로 강등 ──
    # (예: Assessor 가 계속 다운이면 첫 사이클만 보고, 이후엔 HEARTBEAT_CYCLES 마다 재확인)
    HEARTBEAT_CYCLES = int(os.environ.get("GWANJE_LEVEL_HEARTBEAT", "5"))
    why_sig = "|".join(sorted(why))
    suppressed = st.get("suppressed", 0)
    if cycle_report and not report_tier and why_sig and why_sig == st.get("last_why_sig"):
        # 직전과 신호 구성이 동일(=새 변화 없음) → heartbeat 전까지 침묵
        if suppressed + 1 < HEARTBEAT_CYCLES:
            cycle_report = False
            suppressed += 1
        else:
            suppressed = 0  # heartbeat 도달 → 한 번 재경보
    else:
        suppressed = 0

    # ── 상태 갱신 ────────────────────────────────────────────
    new_state = {
        "assessor_down": assessor_down,
        "seen_done": sorted(set(st.get("seen_done", []) + done_now))[-100:],
        "cycles_accum": 0 if report_tier else cycles_accum,
        "idle_streak": idle_streak,
        "ever_active": was_active or live_n > 0,
        "last_ts": snap.get("ts_kst"),
        "last_why_sig": why_sig,
        "suppressed": suppressed,
    }
    json.dump(new_state, open(STATE, "w"), ensure_ascii=False)

    decision = "REPORT" if report_tier else ("CYCLE" if cycle_report else "QUIET")
    rec = {"ts": snap.get("ts_kst"), "decision": decision, "salience": sal,
           "cycle": cycle_report, "report_reasons": reasons,
           "live_battles": live_n, "orphans": len(orphan_ids), "assessor_down": assessor_down}
    with open(TRAIL, "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # ── 출력 ─────────────────────────────────────────────────
    if decision == "REPORT":
        print(f"📋 [{snap.get('ts_kst')}] 보고서 작성 권장 — " + "; ".join(reasons)
              + f"  (salience={sal}; {'; '.join(why)})")
        return 20
    if decision == "CYCLE":
        print(f"📨 [{snap.get('ts_kst')}] 사이클 보고 — salience={sal}: {'; '.join(why)}"
              + (f"  | Assessor DOWN" if assessor_down else "")
              + f"  | 활성(좀비제외)={live_n} 좀비={len(orphan_ids)} 누적={cycles_accum}/{ACCUM_CYCLES}")
        return 10
    print(f"· [{snap.get('ts_kst')}] 조용함 (salience={sal}, 활성={live_n}, 누적={cycles_accum}/{ACCUM_CYCLES})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
