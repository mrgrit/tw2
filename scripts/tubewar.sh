#!/usr/bin/env bash
###############################################################################
# tubewar — 배포/운영 단일 제어 스크립트
#
#   bash scripts/tubewar.sh install      # 라이브러리·패키지 전부 자동 설치
#   bash scripts/tubewar.sh up           # 서버 올리기 (api + ui [+ siem])
#   bash scripts/tubewar.sh down         # 서버 내리기
#   bash scripts/tubewar.sh restart      # 내렸다 올리기
#   bash scripts/tubewar.sh status       # 상태 보기
#   bash scripts/tubewar.sh logs <svc>   # 로그 따라보기 (api|ui|opensearch|dashboards)
#
# 옵션:
#   up --no-siem      # OpenSearch/Dashboards(SIEM) 없이 api+ui 만
#   up --dev          # ui 를 production 빌드 대신 vite dev 로 (자동 리로드)
#
# 설계:
#   - DB 는 sqlite (.data/tubewar.sqlite3) — docker/postgres 불필요, 학생 PC 배포에 적합.
#   - Java 는 OpenSearch 번들 JDK 사용, node 는 install 시 자동 설치.
#   - PID/로그는 runtime/ 에 (gitignore 됨). 6v6 인프라는 절대 건드리지 않는다.
###############################################################################
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

RUNTIME="$ROOT/runtime"
LOGDIR="$RUNTIME/logs"
PIDDIR="$RUNTIME/pids"
DATADIR="$ROOT/.data"
VENV="$ROOT/.venv"

OPENSEARCH_HOME="${OPENSEARCH_HOME:-$HOME/.local/opensearch}"
DASHBOARDS_HOME="${DASHBOARDS_HOME:-$HOME/.local/opensearch-dashboards}"

# 포트 (런타임에 .env override 가능)
API_PORT="${TUBEWAR_API_PORT:-9200}"
UI_PORT="${TUBEWAR_UI_PORT:-5173}"
OS_PORT="${TUBEWAR_OS_PORT:-9201}"
OSD_PORT="${TUBEWAR_OSD_PORT:-5601}"

c_grn() { printf '\033[32m%s\033[0m\n' "$*"; }
c_red() { printf '\033[31m%s\033[0m\n' "$*"; }
c_ylw() { printf '\033[33m%s\033[0m\n' "$*"; }
log()   { printf '\033[36m[tubewar]\033[0m %s\n' "$*"; }
die()   { c_red "[오류] $*"; exit 1; }

mkdir -p "$LOGDIR" "$PIDDIR" "$DATADIR"

# ── 공통 helper ──────────────────────────────────────────────────────────────
pidfile() { echo "$PIDDIR/$1.pid"; }

is_running() {  # is_running <svc>
  local pf; pf="$(pidfile "$1")"
  [ -f "$pf" ] || return 1
  local pid; pid="$(cat "$pf" 2>/dev/null || true)"
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

port_up() {  # port_up <port>
  if command -v curl >/dev/null 2>&1; then
    curl -fsS -o /dev/null --max-time 2 "http://127.0.0.1:$1/" 2>/dev/null && return 0
  fi
  # HTTP 가 아닌 포트 대비: /dev/tcp 로 연결만 확인
  (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null && { exec 3>&- 3<&-; return 0; }
  return 1
}

wait_port() {  # wait_port <port> <label> <timeout_sec>
  local port="$1" label="$2" to="${3:-60}" i=0
  printf '  %s 헬스 대기' "$label"
  while [ "$i" -lt "$to" ]; do
    if port_up "$port"; then echo " ✓"; return 0; fi
    printf '.'; sleep 1; i=$((i+1))
  done
  echo " ✗"
  return 1
}

start_bg() {  # start_bg <svc> <logfile> -- <cmd...>
  local svc="$1" lf="$2"; shift 2
  [ "$1" = "--" ] && shift
  is_running "$svc" && { c_ylw "  $svc 이미 실행 중 (pid $(cat "$(pidfile "$svc")"))"; return 0; }
  local pf; pf="$(pidfile "$svc")"
  # setsid 로 새 세션 리더를 만들고, 리더 자신의 PID(=PGID)를 pidfile 에 기록.
  # exec 로 실제 명령으로 교체 → PID 보존. 정지 시 process group(-PID)째 종료 가능.
  setsid bash -c 'echo $$ > "$1"; shift; exec "$@"' tubewar-launch "$pf" "$@" \
    >>"$lf" 2>&1 < /dev/null &
  sleep 1
  is_running "$svc" || { c_red "  $svc 기동 실패 — 로그: $lf"; tail -n 15 "$lf" 2>/dev/null; return 1; }
  log "  $svc 기동 (pid $(cat "$pf"))  로그: $lf"
}

stop_svc() {  # stop_svc <svc>
  local svc="$1" pf; pf="$(pidfile "$svc")"
  if ! is_running "$svc"; then
    [ -f "$pf" ] && rm -f "$pf"
    return 0
  fi
  local pid; pid="$(cat "$pf")"
  log "  $svc 정지 (pid $pid)"
  # 프로세스 그룹째 종료 (uvicorn/vite/opensearch 의 자식까지)
  kill -TERM "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
  local i=0
  while kill -0 "$pid" 2>/dev/null && [ "$i" -lt 15 ]; do sleep 1; i=$((i+1)); done
  if kill -0 "$pid" 2>/dev/null; then
    c_ylw "    응답 없음 → 강제 종료(KILL)"
    kill -KILL "-$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null || true
  fi
  rm -f "$pf"
}

# ── .env 보장 ────────────────────────────────────────────────────────────────
ensure_env() {
  if [ ! -f "$ROOT/.env" ]; then
    log ".env 생성 (.env.example 기반, sqlite + 랜덤 JWT)"
    cp "$ROOT/.env.example" "$ROOT/.env"
    local secret; secret="$(head -c 48 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 48)"
    # sqlite 로 전환 (docker/postgres 불필요) + JWT 시크릿 주입
    python3 - "$ROOT/.env" "$DATADIR/tubewar.sqlite3" "$secret" <<'PY'
import sys, re
env, db, secret = sys.argv[1], sys.argv[2], sys.argv[3]
txt = open(env, encoding="utf-8").read()
def setk(t, k, v):
    pat = re.compile(rf'^{re.escape(k)}=.*$', re.M)
    return pat.sub(f'{k}={v}', t) if pat.search(t) else t + f'\n{k}={v}\n'
txt = setk(txt, "DATABASE_URL", f"sqlite+aiosqlite:///{db}")
txt = setk(txt, "TUBEWAR_JWT_SECRET", secret)
open(env, "w", encoding="utf-8").write(txt)
PY
    c_ylw "  → .env 의 ADMIN_PASSWORD 등 비밀값을 운영 전 반드시 수정하세요."
  fi
}

# 안전하게 .env 를 환경으로 로드
load_env() {
  ensure_env
  set -a; . "$ROOT/.env"; set +a
}

###############################################################################
# install — 라이브러리·패키지 전부 자동 설치
###############################################################################
cmd_install() {
  log "tubewar 설치 시작 (root: $ROOT)"

  # 1) 시스템 패키지 (python venv/빌드 + node/npm)
  log "[1/5] 시스템 의존성 점검"
  local need_sys=()
  command -v python3 >/dev/null || need_sys+=("python3")
  python3 -c 'import venv' 2>/dev/null || need_sys+=("python3-venv")
  command -v curl >/dev/null || need_sys+=("curl")

  if [ "${#need_sys[@]}" -gt 0 ]; then
    log "  apt 로 설치: ${need_sys[*]}"
    sudo apt-get update -qq
    sudo apt-get install -y -qq python3 python3-venv python3-pip curl ca-certificates
  else
    c_grn "  python3/venv/curl OK"
  fi

  # node/npm — 없으면 NodeSource(LTS) 설치
  if ! command -v npm >/dev/null 2>&1; then
    log "  node/npm 미설치 → NodeSource Node.js 20 LTS 설치"
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo apt-get install -y -qq nodejs
  fi
  command -v npm >/dev/null || die "npm 설치 실패 — 수동 설치 후 재시도하세요."
  c_grn "  node $(node -v)  /  npm $(npm -v)"

  # 2) python venv + 의존성 (aiosqlite 포함된 [dev] 익스트라)
  log "[2/5] python venv + API 의존성"
  [ -d "$VENV" ] || python3 -m venv "$VENV"
  # shellcheck disable=SC1091
  . "$VENV/bin/activate"
  python -m pip install -U pip wheel >/dev/null
  python -m pip install -e "$ROOT/apps/api[dev]"
  deactivate
  c_grn "  API 의존성 설치 완료"

  # 3) UI 의존성 + production 빌드
  log "[3/5] UI 의존성 설치 + 빌드"
  ( cd "$ROOT/apps/ui" && npm install --no-audit --no-fund && npm run build )
  c_grn "  UI 빌드 완료 (apps/ui/dist)"

  # 4) .env
  log "[4/5] .env"
  ensure_env

  # 5) OpenSearch/Dashboards 점검 (선택적)
  log "[5/5] SIEM 엔진 점검"
  if [ -x "$OPENSEARCH_HOME/bin/opensearch" ]; then
    c_grn "  OpenSearch OK ($OPENSEARCH_HOME)"
  else
    c_ylw "  OpenSearch 미발견 ($OPENSEARCH_HOME) — SIEM 없이도 동작. up --no-siem 사용 가능."
  fi
  [ -x "$DASHBOARDS_HOME/bin/opensearch-dashboards" ] \
    && c_grn "  Dashboards OK ($DASHBOARDS_HOME)" \
    || c_ylw "  Dashboards 미발견 — iframe 대시보드는 비활성."

  echo
  c_grn "설치 완료. 서버 올리기:  bash scripts/tubewar.sh up"
}

###############################################################################
# 개별 서비스 기동
###############################################################################
start_opensearch() {
  [ -x "$OPENSEARCH_HOME/bin/opensearch" ] || { c_ylw "  OpenSearch 미설치 — 건너뜀"; return 0; }
  if port_up "$OS_PORT"; then log "  OpenSearch 이미 응답 (:$OS_PORT)"; return 0; fi
  export OPENSEARCH_JAVA_HOME="$OPENSEARCH_HOME/jdk"
  start_bg opensearch "$LOGDIR/opensearch.log" -- \
    "$OPENSEARCH_HOME/bin/opensearch" \
    -Ediscovery.type=single-node \
    -Eplugins.security.disabled=true \
    -Ehttp.port="$OS_PORT"
  wait_port "$OS_PORT" "OpenSearch" 90 || { c_red "  OpenSearch 헬스 실패"; return 1; }
}

start_dashboards() {
  [ -x "$DASHBOARDS_HOME/bin/opensearch-dashboards" ] || { c_ylw "  Dashboards 미설치 — 건너뜀"; return 0; }
  if port_up "$OSD_PORT"; then log "  Dashboards 이미 응답 (:$OSD_PORT)"; return 0; fi
  start_bg dashboards "$LOGDIR/dashboards.log" -- \
    "$DASHBOARDS_HOME/bin/opensearch-dashboards" \
    --server.host=0.0.0.0 --server.port="$OSD_PORT" \
    --opensearch.hosts="http://127.0.0.1:$OS_PORT"
  wait_port "$OSD_PORT" "Dashboards" 120 || c_ylw "  Dashboards 헬스 지연 — 로그 확인($LOGDIR/dashboards.log)"
}

start_api() {
  start_bg api "$LOGDIR/api.log" -- \
    "$VENV/bin/uvicorn" app.main:app \
      --host "${TUBEWAR_API_HOST:-0.0.0.0}" --port "$API_PORT" \
      --app-dir "$ROOT/apps/api"
  wait_port "$API_PORT" "API" 40 || { c_red "  API 헬스 실패 — $LOGDIR/api.log"; tail -n 20 "$LOGDIR/api.log"; return 1; }
}

start_ui() {
  local mode="$1"  # prod | dev
  if [ "$mode" = "dev" ]; then
    start_bg ui "$LOGDIR/ui.log" -- \
      bash -c "cd '$ROOT/apps/ui' && exec npm run dev -- --port $UI_PORT --host 0.0.0.0"
  else
    [ -d "$ROOT/apps/ui/dist" ] || { c_ylw "  dist 없음 → 빌드"; ( cd "$ROOT/apps/ui" && npm run build ); }
    start_bg ui "$LOGDIR/ui.log" -- \
      bash -c "cd '$ROOT/apps/ui' && exec npm run preview -- --port $UI_PORT --host 0.0.0.0"
  fi
  wait_port "$UI_PORT" "UI" 30 || c_ylw "  UI 헬스 지연 — $LOGDIR/ui.log"
}

###############################################################################
# up — 서버 올리기
###############################################################################
cmd_up() {
  local with_siem=1 ui_mode="prod"
  for a in "$@"; do
    case "$a" in
      --no-siem) with_siem=0 ;;
      --dev)     ui_mode="dev" ;;
      *) die "알 수 없는 옵션: $a" ;;
    esac
  done

  [ -d "$VENV" ] || die "venv 없음 — 먼저: bash scripts/tubewar.sh install"
  load_env

  log "서버 올리기 (siem=$with_siem, ui=$ui_mode)"

  if [ "$with_siem" -eq 1 ]; then
    start_opensearch || c_ylw "  OpenSearch 미기동 — SIEM 적재 비활성으로 계속"
    start_dashboards || true
    # OpenSearch 가 떴으면 API 가 SIEM 으로 적재하도록 환경 주입
    if port_up "$OS_PORT"; then
      export OPENSEARCH_URL="http://127.0.0.1:$OS_PORT"
      export OPENSEARCH_DASHBOARDS_URL="http://127.0.0.1:$OSD_PORT"
      export TUBEWAR_LAB_MONITOR="1"
      log "  SIEM 실시간 적재 활성 (OPENSEARCH_URL/LAB_MONITOR)"
    fi
  fi

  start_api
  start_ui "$ui_mode" || c_ylw "  UI 기동 실패 — node/npm 설치 확인(install) 후 재시도. API 는 정상."

  echo
  c_grn "================ tubewar 가동 ================"
  echo "  UI       : http://127.0.0.1:$UI_PORT"
  echo "  API      : http://127.0.0.1:$API_PORT  (health: /health)"
  [ "$with_siem" -eq 1 ] && port_up "$OS_PORT" && echo "  OpenSearch: http://127.0.0.1:$OS_PORT"
  [ "$with_siem" -eq 1 ] && is_running dashboards && echo "  Dashboards: http://127.0.0.1:$OSD_PORT"
  echo "  로그     : $LOGDIR/   |   상태: bash scripts/tubewar.sh status"
  c_grn "============================================="
}

###############################################################################
# down — 서버 내리기
###############################################################################
cmd_down() {
  log "서버 내리기"
  stop_svc ui
  stop_svc api
  stop_svc dashboards
  stop_svc opensearch
  c_grn "전부 정지 완료."
}

###############################################################################
# status
###############################################################################
cmd_status() {
  printf '%-12s %-10s %-8s %s\n' "SERVICE" "STATE" "PID" "PORT/HEALTH"
  printf '%-12s %-10s %-8s %s\n' "-------" "-----" "---" "-----------"
  _row() {  # _row <svc> <port>
    local svc="$1" port="$2" state pid hp
    if is_running "$svc"; then state="running"; pid="$(cat "$(pidfile "$svc")")"; else state="stopped"; pid="-"; fi
    if port_up "$port"; then hp=":$port up"; else hp=":$port down"; fi
    printf '%-12s %-10s %-8s %s\n' "$svc" "$state" "$pid" "$hp"
  }
  _row opensearch "$OS_PORT"
  _row dashboards "$OSD_PORT"
  _row api        "$API_PORT"
  _row ui         "$UI_PORT"
}

###############################################################################
# reset-admin — admin 패스워드 리셋(없으면 생성). DB(.env DATABASE_URL) 대상.
#   reset-admin [email] [newpassword]
###############################################################################
cmd_reset_admin() {
  load_env
  local email="${1:-${ADMIN_EMAIL:-admin@tubewar.app}}"
  local newpass="${2:-}"
  [ -n "$newpass" ] || { read -r -s -p "새 패스워드: " newpass; echo; }
  [ -n "$newpass" ] || die "패스워드가 비었습니다."
  PYTHONPATH="$ROOT/apps/api" "$VENV/bin/python" - "$email" "$newpass" <<'PY'
import sys, asyncio
from sqlalchemy import select
from app.db import SessionLocal
from app.models import User
from app.security import hash_password

email, newpass = sys.argv[1].strip().lower(), sys.argv[2]

async def main():
    async with SessionLocal() as s:
        u = await s.scalar(select(User).where(User.email == email))
        if u is None:
            u = User(email=email, name="admin", role="admin", is_active=True,
                     password_hash=hash_password(newpass))
            s.add(u); action = "생성"
        else:
            u.password_hash = hash_password(newpass)
            u.role = "admin"; u.is_active = True; action = "리셋"
        await s.commit()
        print(f"admin {action} 완료: {email}")

asyncio.run(main())
PY
}

###############################################################################
# logs
###############################################################################
cmd_logs() {
  local svc="${1:-}"
  [ -n "$svc" ] || die "사용법: logs <api|ui|opensearch|dashboards>"
  local lf="$LOGDIR/$svc.log"
  [ -f "$lf" ] || die "로그 없음: $lf"
  exec tail -n 80 -f "$lf"
}

###############################################################################
# dispatch
###############################################################################
case "${1:-help}" in
  install) shift; cmd_install "$@" ;;
  up)      shift; cmd_up "$@" ;;
  down|stop) shift; cmd_down "$@" ;;
  restart) shift; cmd_down; echo; cmd_up "$@" ;;
  status)  shift; cmd_status "$@" ;;
  reset-admin) shift; cmd_reset_admin "$@" ;;
  logs)    shift; cmd_logs "$@" ;;
  help|*)
    cat <<EOF
tubewar 운영 제어:
  bash scripts/tubewar.sh install            # 라이브러리·패키지 전부 자동 설치
  bash scripts/tubewar.sh up [--no-siem] [--dev]
  bash scripts/tubewar.sh down               # 서버 내리기
  bash scripts/tubewar.sh restart [옵션]     # 내렸다 올리기
  bash scripts/tubewar.sh status             # 상태
  bash scripts/tubewar.sh reset-admin [email] [pw]  # admin 패스워드 리셋/생성
  bash scripts/tubewar.sh logs <svc>         # 로그 (api|ui|opensearch|dashboards)
EOF
    ;;
esac
