#!/usr/bin/env bash
# 트랙 grind 감시자 — Monitor(persistent)용. 각 stdout 라인 = 알림(나를 깨움).
# 액션 신호만 방출: ASSESSOR DOWN / GRIND COMPLETE / STALL / 희소 heartbeat.
# usage: track_watch.sh <grind_pid> <ledger_like e.g. soc-w%> <total> <logfile>
GP="$1"; LIKE="$2"; TOTAL="$3"; LOG="$4"
LED=/home/ccc/tw2/.data/verify_ledger.sqlite3
PY=/home/ccc/tubewar/.venv/bin/python3
donecount(){ "$PY" -c "import sqlite3;c=sqlite3.connect('$LED');print(sum(1 for _ in c.execute(\"SELECT 1 FROM scenario_state WHERE scenario_id LIKE '$LIKE' AND status='done'\")))" 2>/dev/null || echo "?"; }
prev=-1; same=0; n=0
while true; do
  if ! kill -0 "$GP" 2>/dev/null; then
    echo "GRIND COMPLETE [$LIKE]: $(tail -1 "$LOG" 2>/dev/null | cut -c1-100)"
    grep -E 'pass[0-9]+ partial|ERR|⚠️|요약' "$LOG" 2>/dev/null | tail -40
    break
  fi
  d=$(donecount)
  ah=$(curl -s -m 8 http://192.168.0.151:9201/health -o /dev/null -w '%{http_code}' 2>/dev/null)
  [ "$ah" != "200" ] && echo "ASSESSOR DOWN (http=$ah) [$LIKE] done=$d/$TOTAL — recreate: cd ~/el34 && docker compose --profile assessor up -d assessor"
  if [ "$d" = "$prev" ]; then same=$((same+1)); else same=0; fi
  prev="$d"
  # 진행 없음(>=3주기 ~ 90분) + grind 살아있음 → 정체 의심
  [ "$same" -ge 3 ] && echo "STALL? [$LIKE] done=$d/$TOTAL no progress ~90m, assessor=$ah, tail: $(tail -1 "$LOG" 2>/dev/null | cut -c1-90)"
  # 희소 heartbeat: 4주기(~2h)마다 1회 생존 신호
  n=$((n+1)); [ $((n % 4)) -eq 1 ] && echo "HEARTBEAT [$LIKE] done=$d/$TOTAL assessor=$ah cur=$(tail -1 "$LOG" 2>/dev/null | cut -c1-70)"
  sleep 1800
done
