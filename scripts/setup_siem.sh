#!/usr/bin/env bash
# tw2 중앙 SIEM 스택 기동 — OpenSearch + OpenSearch Dashboards(+선택 공개 터널) + .env 배선.
#
# bootstrap.sh(core: api/ui/db/systemd) 이후 실행. 멱등 — 재실행해도 안전(기존 컨테이너 재사용).
#   bash scripts/setup_siem.sh            # 로컬(OPENSEARCH_DASHBOARDS_URL=http://127.0.0.1:5602)
#   bash scripts/setup_siem.sh --tunnel   # + cloudflared 공개 터널(원격 브라우저에서 iframe 접근용)
#
# 이후 데모 데이터/백필:
#   .venv/bin/python scripts/seed_demo_cohort.py
#   OPENSEARCH_URL=http://127.0.0.1:9210 .venv/bin/python scripts/backfill_siem.py --cohort 3 --reset
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"
have(){ command -v "$1" >/dev/null 2>&1; }
SUDO=""; [ "$(id -u)" -ne 0 ] && have sudo && SUDO="sudo"
say(){ printf '\033[36m▸ %s\033[0m\n' "$*"; }
warn(){ printf '\033[33m⚠ %s\033[0m\n' "$*"; }

OS_PORT=9210; OSD_PORT=5602; NET=tw2-siem
OS_IMAGE=opensearchproject/opensearch:2.11.1
OSD_IMAGE=opensearchproject/opensearch-dashboards:2.11.1
TUNNEL=0; [ "${1:-}" = "--tunnel" ] && TUNNEL=1

have docker || { warn "docker 필요 — 설치 후 재실행"; exit 1; }
D="$SUDO docker"
ENVF="$REPO/.env"; [ -f "$ENVF" ] || { warn ".env 없음 — 먼저 bootstrap.sh 실행"; exit 1; }

# .env key=value 멱등 upsert
upsert_env(){ local k="$1" v="$2"
  if grep -q "^${k}=" "$ENVF"; then sed -i "s#^${k}=.*#${k}=${v}#" "$ENVF"
  else printf '%s=%s\n' "$k" "$v" >> "$ENVF"; fi; }

# ── 1) 도커 네트워크 ──
$D network inspect "$NET" >/dev/null 2>&1 || { say "네트워크 $NET 생성"; $D network create "$NET" >/dev/null; }

# ── 2) OpenSearch(보안 비활성, 로컬 바인드) ──
if $D ps -a --format '{{.Names}}' | grep -qx tw2-opensearch; then
  say "tw2-opensearch 재사용"; $D start tw2-opensearch >/dev/null 2>&1 || true
  $D network connect "$NET" tw2-opensearch 2>/dev/null || true
else
  say "tw2-opensearch 기동"
  $D run -d --name tw2-opensearch --network "$NET" -p 127.0.0.1:${OS_PORT}:9200 \
    -e discovery.type=single-node -e DISABLE_SECURITY_PLUGIN=true \
    -e "OPENSEARCH_JAVA_OPTS=-Xms512m -Xmx512m" -e bootstrap.memory_lock=false \
    --restart unless-stopped "$OS_IMAGE" >/dev/null
fi

# ── 3) OpenSearch Dashboards(보안 비활성, 임베드 허용) ──
if $D ps -a --format '{{.Names}}' | grep -qx tw2-osd; then
  say "tw2-osd 재사용"; $D start tw2-osd >/dev/null 2>&1 || true
else
  say "tw2-osd 기동"
  $D run -d --name tw2-osd --network "$NET" -p 127.0.0.1:${OSD_PORT}:5601 \
    -e 'OPENSEARCH_HOSTS=["http://tw2-opensearch:9200"]' \
    -e DISABLE_SECURITY_DASHBOARDS_PLUGIN=true \
    -e SERVER_SECURITYRESPONSEHEADERS_DISABLEEMBEDDING=false \
    --restart unless-stopped "$OSD_IMAGE" >/dev/null
fi

# ── 4) 준비 대기 ──
say "OpenSearch 준비 대기…"; i=0
until curl -s "http://127.0.0.1:${OS_PORT}" >/dev/null 2>&1 || [ $i -ge 40 ]; do sleep 3; i=$((i+1)); done
say "Dashboards 준비 대기…"; i=0
until curl -s "http://127.0.0.1:${OSD_PORT}/api/status" 2>/dev/null | grep -q 'overall\|available' || [ $i -ge 60 ]; do sleep 3; i=$((i+1)); done

# ── 5) 공개 터널(선택) ──
DASH_URL="http://127.0.0.1:${OSD_PORT}"
if [ $TUNNEL -eq 1 ]; then
  if have cloudflared; then
    CF="$(command -v cloudflared)"; UNIT=/etc/systemd/system/tw2-osd-tunnel.service
    say "OSD 터널 서비스 설치"
    $SUDO tee "$UNIT" >/dev/null <<UNIT
[Unit]
Description=tw2 OSD Cloudflare Quick Tunnel (public -> OpenSearch Dashboards :${OSD_PORT})
After=network-online.target
Wants=network-online.target
[Service]
User=$(id -un)
ExecStart=/bin/bash -c '${CF} tunnel --no-autoupdate --url http://localhost:${OSD_PORT} 2>&1 | tee ${REPO}/.data/osd-tunnel.log'
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
UNIT
    : > "$REPO/.data/osd-tunnel.log"
    $SUDO systemctl daemon-reload; $SUDO systemctl enable --now tw2-osd-tunnel >/dev/null 2>&1
    say "터널 URL 대기…"; i=0
    until grep -qoE 'https://[a-z0-9-]+\.trycloudflare\.com' "$REPO/.data/osd-tunnel.log" 2>/dev/null || [ $i -ge 25 ]; do sleep 2; i=$((i+1)); done
    U="$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$REPO/.data/osd-tunnel.log" | head -1)"
    if [ -n "$U" ]; then DASH_URL="$U"; else warn "터널 URL 미확보 — 로컬 URL 유지"; fi
  else
    warn "cloudflared 없음 — 터널 생략, 로컬 URL 사용"
  fi
fi

# ── 6) .env 배선 + api 재기동 ──
upsert_env OPENSEARCH_URL "http://127.0.0.1:${OS_PORT}"
upsert_env OPENSEARCH_DASHBOARDS_URL "$DASH_URL"
say ".env 배선: OPENSEARCH_URL=http://127.0.0.1:${OS_PORT} · OPENSEARCH_DASHBOARDS_URL=${DASH_URL}"
if have systemctl && $SUDO systemctl list-units --type=service 2>/dev/null | grep -q tw2-api; then
  $SUDO systemctl restart tw2-api && say "tw2-api 재기동"
else
  warn "tw2-api 서비스 없음 — API 를 수동 재기동하세요(.env 반영)"
fi

cat <<DONE

✅ 중앙 SIEM 스택 준비 완료.
   OpenSearch:            http://127.0.0.1:${OS_PORT}
   OpenSearch Dashboards: ${DASH_URL}

다음(데모 데이터 + SIEM 백필):
   .venv/bin/python scripts/seed_demo_cohort.py
   OPENSEARCH_URL=http://127.0.0.1:${OS_PORT} .venv/bin/python scripts/backfill_siem.py --cohort 3 --reset

⚠ --tunnel 사용 시 quick tunnel URL 은 서비스 재기동마다 바뀝니다.
   바뀌면: .env OPENSEARCH_DASHBOARDS_URL 갱신(이 스크립트 재실행) → tw2-api 재기동.
DONE
