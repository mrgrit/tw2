#!/usr/bin/env python3
"""트랙 배치 그라인드 — 한 트랙의 시나리오들을 solo→duel 순차(병렬 아님)로 검수.

각 시나리오는 play_scenario.run_one 으로 처방 명령 실행 + claude 라이브 채점. 미션 하나씩
순차. 시나리오/모드 단위로 try 감싸 한 건 실패가 배치를 멈추지 않게(원장에 기록). 이미
done 인 (sid,mode)는 건너뜀(이어하기). 진행은 stdout(flush) + 원장에 영속.

usage: python scripts/grind_track.py <track-prefix> [--from N] [--to N] [--modes solo,duel]
"""
import sys, argparse, sqlite3, glob, os.path as osp, traceback
sys.path.insert(0,"scripts"); import play_scenario as ps

LEDGER=".data/verify_ledger.sqlite3"

def track_scenarios(prefix):
    sids=[]
    for p in sorted(glob.glob(f"contents/battle-scenarios/{prefix}*.yaml")):
        sid=osp.splitext(osp.basename(p))[0]
        # only well-formed week scenarios of THIS track (prefix-wNN)
        if sid.startswith(prefix):
            sids.append(sid)
    return sids

def done_modes(sid):
    c=sqlite3.connect(LEDGER)
    r=dict(c.execute("SELECT mode,status FROM scenario_state WHERE scenario_id=?",(sid,)).fetchall())
    c.close(); return {m for m,s in r.items() if s=="done"}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("prefix")
    ap.add_argument("--from",dest="frm",type=int,default=1)
    ap.add_argument("--to",dest="to",type=int,default=15)
    ap.add_argument("--modes",default="solo,duel")
    ap.add_argument("--redo",action="store_true",help="이미 done이어도 다시 실행")
    a=ap.parse_args()
    modes=a.modes.split(",")
    sids=[s for s in track_scenarios(a.prefix)
          if a.frm <= int(s.split("-w")[-1]) <= a.to]
    print(f"[grind] {a.prefix} 시나리오 {len(sids)}개 × {modes} 순차 검수 시작", flush=True)
    summary=[]; consec_allfail=0
    import time as _t
    for sid in sids:
        dm=done_modes(sid)
        for mode in modes:
            if mode in dm and not a.redo:
                print(f"  · {sid}/{mode} 이미 done — skip", flush=True); continue
            try:
                res=ps.run_one(sid, mode)
                summary.append((sid,mode,res["pass"],res["partial"],res["bad"]))
                # 장애 감지: 미션이 돌았는데 pass·partial 0(전부 error) → 채점 장애 의심
                if (res["pass"]+res["partial"])==0 and (res["pass"]+res["partial"]+res["bad"])>0:
                    consec_allfail+=1
                    print(f"  ⚠️ {sid}/{mode} 전부 error — 채점 장애 의심(연속 {consec_allfail})", flush=True)
                    if consec_allfail>=2:
                        print("  !! 연속 전부-error 2회 → 채점 장애로 판단, 배치 중단(개입 필요)", flush=True)
                        raise SystemExit("grading outage detected")
                    print("  … 90s 백오프(레이트/장애 회복 대기)", flush=True); _t.sleep(90)
                else:
                    consec_allfail=0
            except SystemExit: raise
            except Exception as e:
                print(f"  !! {sid}/{mode} 예외: {e}", flush=True)
                traceback.print_exc()
                summary.append((sid,mode,"ERR","ERR","ERR"))
    print("\n=== grind 요약 ===", flush=True)
    for sid,mode,p,pa,b in summary:
        flag=" ⚠️" if (b not in (0,"ERR") or b=="ERR") else ""
        print(f"  {sid}/{mode}: pass{p} partial{pa} bad{b}{flag}", flush=True)

if __name__=="__main__":
    main()
