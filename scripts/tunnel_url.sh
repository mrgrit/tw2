#!/usr/bin/env bash
# tw2 Cloudflare quick tunnel 의 현재 공개 URL 을 출력한다.
# quick tunnel 은 서비스 재시작마다 URL 이 바뀌므로, 접속 전에 이걸로 확인한다.
set -euo pipefail
LOG="/home/ccc/tw2/.data/tunnel.log"
URL="$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG" 2>/dev/null | tail -1 || true)"
if [ -z "$URL" ]; then
  echo "URL 아직 없음 — 터널이 방금 떴다면 몇 초 뒤 다시 실행. (서비스: systemctl status tw2-tunnel)" >&2
  exit 1
fi
echo "$URL"
