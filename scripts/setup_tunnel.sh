#!/usr/bin/env bash
# =============================================================================
# tw2 외부 노출(Cloudflare Quick Tunnel) 설치·기동 — sudo 로 1회 실행.
#
#   - cloudflared 바이너리 확인(없으면 ~/.local/bin 에 설치)
#   - tw2-tunnel.service 등록(→ UI :5173 을 https://*.trycloudflare.com 로 공개)
#   - tw2-ui 재시작(vite allowedHosts 반영)
#   - 발급된 공개 URL 출력
#
# 사용:  sudo bash scripts/setup_tunnel.sh
# 해제:  sudo systemctl disable --now tw2-tunnel
# =============================================================================
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
BIN=/home/ccc/.local/bin/cloudflared

if [ ! -x "$BIN" ]; then
  echo "[tunnel] cloudflared 설치"
  install -d -o ccc -g ccc /home/ccc/.local/bin
  sudo -u ccc curl -fsSL -o "$BIN" \
    https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
  chmod +x "$BIN"
fi
"$BIN" --version

echo "[tunnel] systemd 유닛 등록"
install -m 0644 "$REPO/scripts/tw2-tunnel.service" /etc/systemd/system/tw2-tunnel.service
systemctl daemon-reload

echo "[tunnel] tw2-ui 재시작(allowedHosts 반영)"
systemctl restart tw2-ui

echo "[tunnel] tw2-tunnel 기동"
systemctl enable --now tw2-tunnel
systemctl restart tw2-tunnel   # 이미 떠 있었다면 새 URL 재발급

echo "[tunnel] 공개 URL 대기..."
URL=""
for i in $(seq 1 20); do
  URL="$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' /home/ccc/tw2/.data/tunnel.log 2>/dev/null | tail -1 || true)"
  [ -n "$URL" ] && break
  sleep 1
done

echo
if [ -n "$URL" ]; then
  echo "======================================================================"
  echo " tw2 외부 접속 URL:  $URL"
  echo " (재시작마다 바뀜 → 이후 조회: bash scripts/tunnel_url.sh)"
  echo "======================================================================"
else
  echo "URL 미발급 — 로그 확인: journalctl -u tw2-tunnel -n 30"
  exit 1
fi
