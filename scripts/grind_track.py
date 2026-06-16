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
    summary=[]
    import time as _t
    def allfail(res): return (res["pass"]+res["partial"])==0 and (res["pass"]+res["partial"]+res["bad"])>0
    for sid in sids:
        dm=done_modes(sid)
        for mode in modes:
            if mode in dm and not a.redo:
                print(f"  · {sid}/{mode} 이미 done — skip", flush=True); continue
            # 자가복구: 전부-error(일시 채점장애 윈도우)면 장시간 백오프 후 같은 시나리오 재시도(최대 3회).
            res=None
            for attempt in range(1, 4):
                try:
                    res=ps.run_one(sid, mode)
                except Exception as e:
                    print(f"  !! {sid}/{mode} 예외(시도{attempt}): {e}", flush=True); traceback.print_exc()
                    res=None
                if res and not allfail(res):
                    break
                if attempt < 3:
                    wait=900*attempt   # 240s, 480s — claude 윈도우 회복 대기
                    print(f"  ⚠️ {sid}/{mode} 전부 error/예외 — 일시 채점장애 의심, {wait}s 백오프 후 재시도({attempt}/3)", flush=True)
                    _t.sleep(wait)
            if res: summary.append((sid,mode,res["pass"],res["partial"],res["bad"]))
            else:   summary.append((sid,mode,"ERR","ERR","ERR"))
    print("\n=== grind 요약 ===", flush=True)
    for sid,mode,p,pa,b in summary:
        flag=" ⚠️" if (b not in (0,"ERR") or b=="ERR") else ""
        print(f"  {sid}/{mode}: pass{p} partial{pa} bad{b}{flag}", flush=True)

if __name__=="__main__":
    main()
