#!/usr/bin/env bash
###############################################################################
# gpu-vpn — GlobalProtect VPN(openconnect)로 GPU(Ollama) 서버에 접속.
#
#   bash scripts/gpu-vpn.sh install   # openconnect 설치 (sudo 필요)
#   bash scripts/gpu-vpn.sh up        # VPN 연결 (sudo 필요, 백그라운드)
#   bash scripts/gpu-vpn.sh down      # VPN 해제
#   bash scripts/gpu-vpn.sh status    # tun 상태 + GPU 도달/모델 테스트
#
# 자격증명은 .env(gitignored)에서 읽는다 — 코드/커밋에 비밀 금지:
#   VPN_PORTAL=106.240.19.114
#   VPN_USER=mrgrit
#   VPN_PASS=********
# GPU 주소(테스트용) 기본값: 211.170.162.139:10934  (GPU_HOST/GPU_PORT 로 override)
#
# 비고: GlobalProtect 는 Linux 공식 클라이언트 대신 FOSS openconnect 의 GP 프로토콜로
#       접속한다. 포털이 SAML/OTP(2FA)를 강제하면 1회는 대화형 연결이 필요할 수 있다.
###############################################################################
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
PIDDIR="$ROOT/runtime/pids"; mkdir -p "$PIDDIR"
VPNPID="$PIDDIR/vpn.pid"
GPU_HOST="${GPU_HOST:-211.170.162.139}"
GPU_PORT="${GPU_PORT:-10934}"

load_env() { [ -f "$ROOT/.env" ] && { set -a; . "$ROOT/.env"; set +a; }; }

gpu_test() {
  if timeout 6 bash -c "(exec 3<>/dev/tcp/$GPU_HOST/$GPU_PORT)" 2>/dev/null; then
    echo "  GPU $GPU_HOST:$GPU_PORT 도달 가능 ✓"
    echo -n "  ollama /api/tags → "
    curl -fsS --max-time 10 "http://$GPU_HOST:$GPU_PORT/api/tags" 2>/dev/null | head -c 400 || echo "(응답 없음)"
    echo
  else
    echo "  GPU $GPU_HOST:$GPU_PORT 도달 불가 ✗ (VPN 미연결일 수 있음)"
  fi
}

case "${1:-help}" in
  install)
    echo "[gpu-vpn] openconnect 설치 (sudo)"
    sudo apt-get update -qq
    sudo apt-get install -y openconnect
    openconnect --version 2>&1 | head -1
    ;;
  up)
    load_env
    : "${VPN_PORTAL:?.env 에 VPN_PORTAL 필요}"
    : "${VPN_USER:?.env 에 VPN_USER 필요}"
    : "${VPN_PASS:?.env 에 VPN_PASS 필요}"
    command -v openconnect >/dev/null || { echo "openconnect 미설치 — 먼저: bash scripts/gpu-vpn.sh install"; exit 1; }
    if [ -f "$VPNPID" ] && kill -0 "$(cat "$VPNPID")" 2>/dev/null; then
      echo "[gpu-vpn] 이미 연결됨 (pid $(cat "$VPNPID"))"; gpu_test; exit 0
    fi
    echo "[gpu-vpn] GlobalProtect 연결: $VPN_USER@$VPN_PORTAL ..."
    # GP 프로토콜, 비밀번호는 stdin 으로(프로세스 목록 노출 방지), 백그라운드 데몬화.
    printf '%s\n' "$VPN_PASS" | sudo openconnect --protocol=gp --user="$VPN_USER" \
      --passwd-on-stdin --background --pid-file="$VPNPID" "$VPN_PORTAL"
    sleep 5
    echo "[gpu-vpn] 상태:"; ip -o link show 2>/dev/null | grep -iE "tun|gpd" || echo "  tun 인터페이스 없음"
    gpu_test
    ;;
  down)
    if [ -f "$VPNPID" ] && kill -0 "$(cat "$VPNPID")" 2>/dev/null; then
      sudo kill "$(cat "$VPNPID")" 2>/dev/null || true; rm -f "$VPNPID"; echo "[gpu-vpn] VPN 해제"
    else
      sudo pkill openconnect 2>/dev/null || true; rm -f "$VPNPID"; echo "[gpu-vpn] VPN 해제(pidfile 없음 → openconnect 종료 시도)"
    fi
    ;;
  status)
    ip -o link show 2>/dev/null | grep -iE "tun|gpd" || echo "  tun 인터페이스 없음"
    gpu_test
    ;;
  *)
    cat <<EOF
GPU VPN (GlobalProtect / openconnect):
  bash scripts/gpu-vpn.sh install   # openconnect 설치 (sudo)
  bash scripts/gpu-vpn.sh up        # VPN 연결 (sudo, 백그라운드)
  bash scripts/gpu-vpn.sh down      # VPN 해제
  bash scripts/gpu-vpn.sh status    # 상태 + GPU 도달 테스트
자격증명(.env): VPN_PORTAL / VPN_USER / VPN_PASS
EOF
    ;;
esac
