#!/usr/bin/env python3
"""레거시(one-off) 시나리오 그라인드 — 공유 prefix 가 없어 명시적 리스트로 solo→duel 순차 검수.
grind_track 과 동일한 자가복구(전부-error 백오프 재시도)·이어하기(done skip)·원장 기록.

usage: python scripts/grind_legacy.py [--redo] [--modes solo,duel] [--only sidA,sidB]
"""
import sys, argparse, sqlite3, time, traceback
sys.path.insert(0,"scripts"); import play_scenario as ps

LEDGER=".data/verify_ledger.sqlite3"
LEGACY=["apt-phase1","apt-phase2","apt-phase3","bruteforce-vs-lockout","championship",
        "cohort-cross-infra-demo","dos-vs-resilience","exfil-vs-dlp","incident-response",
        "lateral-vs-segmentation","live-healthcheck","precinct6-data-theft","precinct6-phishing",
        "privesc-vs-hardening","purple-team","recon-vs-detect","sqli-vs-waf",
        "webshell-vs-integrity","xss-vs-filter"]

def done_modes(sid):
    c=sqlite3.connect(LEDGER)
    r=dict(c.execute("SELECT mode,status FROM scenario_state WHERE scenario_id=?",(sid,)).fetchall())
    c.close(); return {m for m,s in r.items() if s=="done"}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--modes",default="solo,duel")
    ap.add_argument("--redo",action="store_true")
    ap.add_argument("--only",default="")
    a=ap.parse_args()
    modes=a.modes.split(",")
    sids=[s for s in LEGACY if (not a.only or s in a.only.split(","))]
    print(f"[legacy] {len(sids)}개 시나리오 × {modes} 순차 검수", flush=True)
    def allfail(res): return (res["pass"]+res["partial"])==0 and (res["pass"]+res["partial"]+res["bad"])>0
    summary=[]
    for sid in sids:
        dm=done_modes(sid)
        for mode in modes:
            if mode in dm and not a.redo:
                print(f"  · {sid}/{mode} 이미 done — skip", flush=True); continue
            res=None
            for attempt in range(1,4):
                try: res=ps.run_one(sid,mode)
                except Exception as e:
                    print(f"  !! {sid}/{mode} 예외(시도{attempt}): {e}", flush=True); traceback.print_exc(); res=None
                if res and not allfail(res): break
                if attempt<3:
                    wait=900*attempt
                    print(f"  ⚠️ {sid}/{mode} 전부 error — {wait}s 백오프 후 재시도({attempt}/3)", flush=True); time.sleep(wait)
            summary.append((sid,mode,res["pass"],res["partial"],res["bad"]) if res else (sid,mode,"ERR","ERR","ERR"))
    print("\n=== legacy grind 요약 ===", flush=True)
    for sid,mode,p,pa,b in summary:
        flag=" ⚠️" if (b not in (0,) ) else ""
        print(f"  {sid}/{mode}: pass{p} partial{pa} bad{b}{flag}", flush=True)

if __name__=="__main__": main()
