#!/usr/bin/env python3
"""검수 진행 원장 — 시나리오×모드×미션 단위로 라이브 채점 결과를 영속 추적.

다중 세션 그라인드(병렬 금지, 하나씩)를 세션 리셋에도 이어가기 위한 상태 저장소.

명령:
  python scripts/verify_ledger.py init     # YAML 145개에서 행 생성(멱등)
  python scripts/verify_ledger.py status    # 트랙/모드별 진행 요약
  python scripts/verify_ledger.py next       # 다음 미검수 시나리오 1개
  python scripts/verify_ledger.py show <scenario_id>
"""
import sys, os, glob, sqlite3, json
import yaml

ROOT = os.path.join(os.path.dirname(__file__), "..")
LEDGER = os.path.join(ROOT, ".data", "verify_ledger.sqlite3")
SCN_DIR = os.path.join(ROOT, "contents", "battle-scenarios")

DDL = """
CREATE TABLE IF NOT EXISTS missions(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  scenario_id TEXT NOT NULL,
  track TEXT,
  mode TEXT NOT NULL,            -- solo | duel
  side TEXT NOT NULL,            -- red | blue
  mission_order INTEGER NOT NULL,
  points INTEGER,
  status TEXT NOT NULL DEFAULT 'pending',  -- pending|pass|partial|fail|error|fixed|skip
  awarded INTEGER,
  verdict TEXT,
  battle_id INTEGER,
  submission_id INTEGER,
  attempts INTEGER NOT NULL DEFAULT 0,
  notes TEXT,
  updated_at TEXT,
  UNIQUE(scenario_id, mode, side, mission_order)
);
CREATE TABLE IF NOT EXISTS scenario_state(
  scenario_id TEXT NOT NULL,
  mode TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending', -- pending|done|fixing
  battle_id INTEGER,
  notes TEXT,
  updated_at TEXT,
  PRIMARY KEY(scenario_id, mode)
);
"""

def conn():
    c = sqlite3.connect(LEDGER)
    c.executescript(DDL)
    return c

def track_of(fid):
    import re
    m = re.match(r"([a-z]+(?:-[a-z]+)*)-w\d+$", fid)
    return m.group(1) if m else "legacy-misc"

def cmd_init():
    c = conn(); n=0
    for path in sorted(glob.glob(os.path.join(SCN_DIR, "*.yaml"))):
        with open(path) as f:
            try: d = yaml.safe_load(f)
            except Exception: continue
        if not isinstance(d, dict): continue
        sid = d.get("id") or os.path.splitext(os.path.basename(path))[0]
        tr = track_of(os.path.splitext(os.path.basename(path))[0])
        for mode in ("solo", "duel"):
            c.execute("INSERT OR IGNORE INTO scenario_state(scenario_id,mode,status,updated_at) VALUES(?,?,?,datetime('now'))",(sid,mode,"pending"))
            for side, key in (("red","red_missions"),("blue","blue_missions")):
                for m in (d.get(key) or []):
                    c.execute(
                        "INSERT OR IGNORE INTO missions(scenario_id,track,mode,side,mission_order,points,updated_at)"
                        " VALUES(?,?,?,?,?,?,datetime('now'))",
                        (sid, tr, mode, side, m.get("order"), m.get("points")))
                    n += c.execute("SELECT changes()").fetchone()[0]
    c.commit()
    tot = c.execute("SELECT count(*) FROM missions").fetchone()[0]
    print(f"init 완료. 신규 {n}행, 총 {tot}행 (시나리오×모드×미션).")

def cmd_status():
    c = conn()
    print("=== 트랙×모드 진행 (pass/partial/fail/error/pending / 총) ===")
    rows = c.execute("""SELECT track,mode,
      sum(status='pass'),sum(status='partial'),sum(status='fail'),
      sum(status='error'),sum(status='pending'),count(*)
      FROM missions GROUP BY track,mode ORDER BY track,mode""").fetchall()
    print(f"{'track':16} {'mode':5} {'pass':>5}{'part':>5}{'fail':>5}{'err':>5}{'pend':>6}{'tot':>6}")
    for r in rows:
        print(f"{r[0]:16} {r[1]:5} {r[2] or 0:>5}{r[3] or 0:>5}{r[4] or 0:>5}{r[5] or 0:>5}{r[6] or 0:>6}{r[7]:>6}")
    g = c.execute("SELECT status,count(*) FROM missions GROUP BY status").fetchall()
    print("\n전체:", dict(g))
    sc = c.execute("SELECT mode,status,count(*) FROM scenario_state GROUP BY mode,status").fetchall()
    print("시나리오 상태:", sc)

def cmd_next():
    c = conn()
    r = c.execute("""SELECT scenario_id,mode FROM scenario_state
      WHERE status='pending' ORDER BY
      CASE WHEN mode='solo' THEN 0 ELSE 1 END, scenario_id LIMIT 1""").fetchone()
    print(json.dumps({"scenario_id":r[0],"mode":r[1]} if r else None, ensure_ascii=False))

def cmd_show(sid):
    c = conn()
    for r in c.execute("SELECT mode,side,mission_order,points,status,awarded,verdict,attempts,notes FROM missions WHERE scenario_id=? ORDER BY mode,side,mission_order",(sid,)):
        print(r)

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv)>1 else "status"
    if cmd=="init": cmd_init()
    elif cmd=="status": cmd_status()
    elif cmd=="next": cmd_next()
    elif cmd=="show": cmd_show(sys.argv[2])
    else: print(__doc__)
