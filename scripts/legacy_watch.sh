GP="$1"; LOG="$2"
LED=/home/ccc/tw2/.data/verify_ledger.sqlite3
PY="$(command -v python3)"
TARGET_IP="${TUBEWAR_REF_TARGET_IP:-$(grep -oP '^TUBEWAR_REF_TARGET_IP=\K.*' /home/ccc/tw2/.env 2>/dev/null)}"; TARGET_IP="${TARGET_IP:-192.168.0.80}"
SIDS="apt-phase1 apt-phase2 apt-phase3 bruteforce-vs-lockout championship cohort-cross-infra-demo dos-vs-resilience exfil-vs-dlp incident-response lateral-vs-segmentation live-healthcheck precinct6-data-theft precinct6-phishing privesc-vs-hardening purple-team recon-vs-detect sqli-vs-waf webshell-vs-integrity xss-vs-filter"
inq=$(echo "$SIDS"|tr ' ' ','|sed "s/[^,]*/'&'/g")
dc(){ "$PY" -c "import sqlite3;print(sum(1 for _ in sqlite3.connect('$LED').execute(\"SELECT 1 FROM scenario_state WHERE scenario_id IN ($inq) AND status='done'\")))"; }
prev=-1; same=0; n=0
while true; do
  if ! kill -0 "$GP" 2>/dev/null; then echo "LEGACY GRIND COMPLETE: $(tail -1 "$LOG"|cut -c1-90)"; grep -E '요약|ERR|⚠️' "$LOG"|tail -25; break; fi
  d=$(dc); ah=$(curl -s -m 8 "http://$TARGET_IP:9201/health" -o /dev/null -w '%{http_code}' 2>/dev/null)
  [ "$ah" != "200" ] && echo "ASSESSOR DOWN(http=$ah) legacy done=$d/38"
  [ "$d" = "$prev" ] && same=$((same+1)) || same=0; prev="$d"
  [ "$same" -ge 3 ] && echo "STALL? legacy done=$d/38 ~90m, assessor=$ah, tail:$(tail -1 "$LOG"|cut -c1-80)"
  n=$((n+1)); [ $((n % 4)) -eq 1 ] && echo "HEARTBEAT legacy done=$d/38 assessor=$ah cur=$(tail -1 "$LOG"|cut -c1-70)"
  sleep 1800
done
