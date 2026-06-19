#!/usr/bin/env bash
# =============================================================================
# tw2 한방 부트스트랩 — 초기 설치 리눅스에서 플랫폼(API+UI+DB)을 자동 구축.
#
#   - 시스템 패키지(python3·venv·node20·git·sqlite·빌드도구) 설치
#   - python venv + 의존성(apps/api[dev], aiosqlite 포함)
#   - UI 의존성 설치 + 빌드
#   - .env 자동 생성(SQLite·랜덤 JWT·관리자·포트, 0.0.0.0 바인딩)
#   - DB 초기화(앱 startup이 스키마+관리자+시나리오 자동 시드)
#   - systemd 서비스(tw2-api / tw2-ui) 등록·기동 (없으면 nohup)
#
# 사용:
#   sudo bash scripts/bootstrap.sh                 # 전체 자동(권장)
#   bash scripts/bootstrap.sh --no-systemd         # systemd 없이 nohup
#   TW2_API_PORT=9301 TW2_UI_PORT=5174 bash scripts/bootstrap.sh
#   bash scripts/bootstrap.sh --demo-users         # shin/kim/mrgrit 학생 시드
#
# 환경변수(override):
#   TW2_API_PORT(9200) TW2_UI_PORT(5173) TW2_HOST(0.0.0.0)
#   TW2_ADMIN_EMAIL(admin@tubewar.app) TW2_ADMIN_PASSWORD(자동생성) TW2_ADMIN_NAME(admin)
# =============================================================================
set -euo pipefail

# ---------- 경로/설정 ----------
REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"
API_PORT="${TW2_API_PORT:-9200}"
UI_PORT="${TW2_UI_PORT:-5173}"
HOST="${TW2_HOST:-0.0.0.0}"
ADMIN_EMAIL="${TW2_ADMIN_EMAIL:-admin@tubewar.app}"
ADMIN_NAME="${TW2_ADMIN_NAME:-admin}"
ADMIN_PASSWORD="${TW2_ADMIN_PASSWORD:-}"
USE_SYSTEMD=1; DEMO_USERS=0; UI_MODE="build"
for a in "$@"; do case "$a" in
  --no-systemd) USE_SYSTEMD=0;;
  --demo-users) DEMO_USERS=1;;
  --dev-ui)     UI_MODE="dev";;
  -h|--help)    sed -n '2,30p' "$0"; exit 0;;
esac; done

RUN_USER="${SUDO_USER:-$(id -un)}"
say(){ printf '\n\033[1;36m[bootstrap]\033[0m %s\n' "$*"; }
have(){ command -v "$1" >/dev/null 2>&1; }
SUDO=""; [ "$(id -u)" -ne 0 ] && have sudo && SUDO="sudo"

# ---------- 1) 시스템 패키지 ----------
say "1/7 시스템 패키지 설치"
if have apt-get; then
  $SUDO apt-get update -y
  $SUDO apt-get install -y python3 python3-venv python3-pip python3-dev \
      git curl ca-certificates build-essential sqlite3 openssl
  if ! have node || [ "$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null||echo 0)" -lt 18 ]; then
    say "  Node.js 20 (NodeSource) 설치"
    curl -fsSL https://deb.nodesource.com/setup_20.x | $SUDO -E bash -
    $SUDO apt-get install -y nodejs
  fi
elif have dnf; then
  $SUDO dnf install -y python3 python3-pip python3-devel git curl gcc gcc-c++ make sqlite openssl
  have node || $SUDO dnf module install -y nodejs:20/common || $SUDO dnf install -y nodejs
else
  echo "지원 안 되는 패키지매니저(apt/dnf 아님). python3.10+/node18+/git/sqlite 수동 설치 후 --no-* 로 재실행"; exit 1
fi
say "  python=$(python3 -V 2>&1) node=$(node -v 2>&1) npm=$(npm -v 2>&1)"

# ---------- 2) .env 생성 ----------
say "2/7 .env 생성"
if [ ! -f .env ]; then
  [ -z "$ADMIN_PASSWORD" ] && ADMIN_PASSWORD="$(openssl rand -base64 12 2>/dev/null | tr -d '/+=' | cut -c1-16)"
  JWT="$(openssl rand -hex 32 2>/dev/null || python3 -c 'import secrets;print(secrets.token_hex(32))')"
  cat > .env <<ENV
TUBEWAR_API_HOST=$HOST
TUBEWAR_API_PORT=$API_PORT
TUBEWAR_API_KEY=tw2-api-key-$(date +%Y 2>/dev/null || echo 2026)
TUBEWAR_JWT_SECRET=$JWT
TUBEWAR_JWT_EXPIRES_HOURS=720
DATABASE_URL=sqlite+aiosqlite:///$REPO/.data/tw2.sqlite3
ADMIN_EMAIL=$ADMIN_EMAIL
ADMIN_PASSWORD=$ADMIN_PASSWORD
ADMIN_NAME=$ADMIN_NAME
TUBEWAR_ANALYZER_MODEL=claude-sonnet-4-6
TUBEWAR_GRADE_TIMEOUT=200
TUBEWAR_GRADE_ROUNDS=1
TUBEWAR_LAB_MONITOR=0
ENV
  echo "ADMIN_PW:$ADMIN_PASSWORD" > .admin-credentials.txt; chmod 600 .admin-credentials.txt
  say "  .env 생성됨 (관리자 비번 → .admin-credentials.txt)"
else
  say "  기존 .env 유지"
  API_PORT="$(grep -oP '^TUBEWAR_API_PORT=\K.*' .env || echo "$API_PORT")"
fi
mkdir -p .data

# ---------- 3) python venv + 의존성 ----------
say "3/7 python venv + 의존성(apps/api[dev])"
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
python -m pip install -q -U pip wheel
python -m pip install -q -e "apps/api[dev]"

# ---------- 4) UI 의존성 + 빌드 ----------
say "4/7 UI 의존성 + 빌드"
( cd apps/ui && (npm ci 2>/dev/null || npm install) )
if [ "$UI_MODE" = "build" ]; then ( cd apps/ui && npm run build ); fi

# ---------- 5) DB 초기화(앱 startup이 스키마+관리자+시나리오 시드) ----------
say "5/7 DB 초기화 (스키마+관리자+시나리오 자동 시드)"
set -a; . ./.env; set +a
( python -c "
import asyncio,sys; sys.path.insert(0,'apps/api')
from app.main import lifespan, app
async def go():
    async with lifespan(app): pass
asyncio.run(go())
" ) && say "  DB 시드 완료: .data/tw2.sqlite3"

# ---------- 6) 데모 학생(옵션) ----------
if [ "$DEMO_USERS" = "1" ]; then
  say "6/7 데모 학생 시드 (shin/kim/mrgrit)"
  python -c "
import asyncio,sys; sys.path.insert(0,'apps/api')
from app.db import SessionLocal
from app.models import User
from app.security import hash_password
from sqlalchemy import select
USERS=[('shin@ync.ac.kr','Shin','shin1234'),('kim@ync.ac.kr','Kim','kim12345'),('mrgrit@ync.ac.kr','Mrgrit','mrgrit1234')]
async def go():
    async with SessionLocal() as s:
        for em,nm,pw in USERS:
            if not await s.scalar(select(User).where(User.email==em)):
                s.add(User(email=em,name=nm,password_hash=hash_password(pw),role='student'))
        await s.commit()
asyncio.run(go()); print('  데모 학생 시드 완료(비번: shin1234/kim12345/mrgrit1234)')
"
else
  say "6/7 데모 학생 생략 (--demo-users 로 활성화; 학생은 UI 회원가입 가능)"
fi

# ---------- 7) 서비스 기동 (systemd 또는 nohup) ----------
NODE_BIN="$(command -v node)"; NPM_BIN="$(command -v npm)"
UI_START="$NPM_BIN run preview -- --host $HOST --port $UI_PORT"
[ "$UI_MODE" = "dev" ] && UI_START="$NPM_BIN run dev -- --host $HOST --port $UI_PORT"
if [ "$USE_SYSTEMD" = "1" ] && have systemctl && [ -d /run/systemd/system ]; then
  say "7/7 systemd 서비스 등록(tw2-api / tw2-ui)"
  $SUDO tee /etc/systemd/system/tw2-api.service >/dev/null <<UNIT
[Unit]
Description=tw2 API (uvicorn)
After=network.target
[Service]
User=$RUN_USER
WorkingDirectory=$REPO
EnvironmentFile=$REPO/.env
ExecStart=$REPO/.venv/bin/uvicorn app.main:app --host $HOST --port $API_PORT --app-dir apps/api
Restart=always
[Install]
WantedBy=multi-user.target
UNIT
  $SUDO tee /etc/systemd/system/tw2-ui.service >/dev/null <<UNIT
[Unit]
Description=tw2 UI (vite)
After=network.target tw2-api.service
[Service]
User=$RUN_USER
WorkingDirectory=$REPO/apps/ui
Environment=VITE_API_TARGET=http://127.0.0.1:$API_PORT
Environment=PATH=$(dirname "$NODE_BIN"):/usr/bin:/bin
ExecStart=$UI_START
Restart=always
[Install]
WantedBy=multi-user.target
UNIT
  $SUDO systemctl daemon-reload
  $SUDO systemctl enable --now tw2-api tw2-ui
  sleep 3; $SUDO systemctl --no-pager --lines=0 status tw2-api tw2-ui || true
else
  say "7/7 nohup 기동(systemd 미사용)"
  nohup .venv/bin/uvicorn app.main:app --host "$HOST" --port "$API_PORT" --app-dir apps/api > .data/api.log 2>&1 &
  ( cd apps/ui && VITE_API_TARGET="http://127.0.0.1:$API_PORT" nohup $UI_START > "$REPO/.data/ui.log" 2>&1 & )
  sleep 5
fi

# ---------- 완료 안내 ----------
IP="$(hostname -I 2>/dev/null | awk '{print $1}')"; IP="${IP:-<서버IP>}"
ADMIN_PW_SHOW="$(grep -oP '^ADMIN_PASSWORD=\K.*' .env 2>/dev/null || echo '(.env 참조)')"
cat <<DONE

============================================================
 ✅ tw2 구축 완료
------------------------------------------------------------
 웹 UI :  http://$IP:$UI_PORT
 API   :  http://$IP:$API_PORT   (health: /health)
 관리자:  $ADMIN_EMAIL  /  $ADMIN_PW_SHOW
 학생  :  UI 회원가입$([ "$DEMO_USERS" = 1 ] && echo " (또는 데모: mrgrit@ync.ac.kr / mrgrit1234)")
------------------------------------------------------------
 ⚠️ 자동채점은 'claude' CLI(+TUBEWAR_ANALYZER_MODEL)가 PATH에 있어야 동작.
    없으면 플랫폼은 정상 작동하되 채점은 보류(review)됨.
 ⚠️ 인프라(타깃/공격자)는 배포 환경마다 다르므로 UI/API 로 등록 필요.
 서비스:  systemctl restart tw2-api tw2-ui   (또는 .data/*.log 확인)
============================================================
DONE
