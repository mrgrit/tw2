#!/usr/bin/env bash
# =============================================================================
# tw2-ui(vite) 에 커스텀 도메인 Host 허용 — sudo 로 1회 실행.
#
#   vite 는 알 수 없는 Host 헤더를 403 으로 차단한다(vite.config.ts allowedHosts).
#   고정 도메인(Cloudflare Named Tunnel 등)을 붙일 때 TW2_ALLOWED_HOSTS 를
#   systemd drop-in 으로 주입한다. drop-in 이라 bootstrap.sh 가 tw2-ui.service
#   본문을 다시 써도 유지된다.
#
# 사용:  sudo bash scripts/allow_ui_host.sh [host[,host...]]
#        (기본: tubewar.dawnofagi.cloud)
# 해제:  sudo rm /etc/systemd/system/tw2-ui.service.d/allowed-hosts.conf
#        && sudo systemctl daemon-reload && sudo systemctl restart tw2-ui
# =============================================================================
set -euo pipefail
HOSTS="${1:-tubewar.dawnofagi.cloud}"
DROPIN=/etc/systemd/system/tw2-ui.service.d

install -d -m 0755 "$DROPIN"
cat > "$DROPIN/allowed-hosts.conf" <<UNIT
[Service]
Environment=TW2_ALLOWED_HOSTS=$HOSTS
UNIT

systemctl daemon-reload
systemctl restart tw2-ui

echo "[ui] Host 허용 확인..."
FIRST="${HOSTS%%,*}"
CODE=000
for i in $(seq 1 20); do
  CODE="$(curl -s -m 3 -o /dev/null -w '%{http_code}' -H "Host: $FIRST" http://127.0.0.1:5173/ || true)"
  [ "$CODE" = "200" ] && break
  sleep 1
done
echo "[ui] Host=$FIRST → HTTP $CODE"
[ "$CODE" = "200" ]
