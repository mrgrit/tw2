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

# user-space 단계(venv/pip/npm/DB시드)는 항상 RUN_USER 권한으로 실행한다.
# sudo 로 부트스트랩하면 .venv·.data·egg-info·node_modules 가 root 소유가 되어
#  (1) 비루트로 재실행 시 pip 가 'Cannot update time stamp ... egg-info' 로 실패하고
#  (2) systemd 서비스(User=RUN_USER)가 root 소유 SQLite DB 에 write 못해 런타임이 깨진다.
AS_USER(){
  if [ "$(id -u)" -eq 0 ] && [ "$RUN_USER" != "root" ]; then
    sudo -u "$RUN_USER" -H env "PATH=$PATH" "$@"
  else
    "$@"
  fi
}
# 이전에 root 소유로 남은 빌드 산출물을 RUN_USER 로 자가복구(있을 때만).
heal_owner(){
  [ "$(id -u)" -eq 0 ] && [ "$RUN_USER" != "root" ] || return 0
  chown -R "$RUN_USER" .venv .data apps/api/*.egg-info apps/ui/node_modules 2>/dev/null || true
}

# ---------- 1) 시스템 패키지 ----------
say "1/7 시스템 패키지 설치"
if have apt-get; then
  $SUDO apt-get update -y
  $SUDO apt-get install -y python3 python3-venv python3-pip python3-dev \
      git curl ca-certificates build-essential sqlite3 openssl libffi-dev libssl-dev
  if ! have node || [ "$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null||echo 0)" -lt 18 ]; then
    say "  Node.js 20 (NodeSource) 설치"
    if curl -fsSL https://deb.nodesource.com/setup_20.x | $SUDO -E bash -; then
      $SUDO apt-get install -y nodejs
    else
      say "  ⚠ NodeSource 실패 → 배포판 nodejs+npm 로 폴백"
      $SUDO apt-get install -y nodejs npm
    fi
  fi
  # 일부 배포판은 nodejs 패키지에 npm 이 없다 → 별도 보장.
  have npm || $SUDO apt-get install -y npm || true
elif have dnf; then
  $SUDO dnf install -y python3 python3-pip python3-devel git curl gcc gcc-c++ make sqlite openssl libffi-devel openssl-devel
  have node || $SUDO dnf module install -y nodejs:20/common || $SUDO dnf install -y nodejs
  have npm || $SUDO dnf install -y npm || true
else
  echo "지원 안 되는 패키지매니저(apt/dnf 아님). python3.10+/node18+/git/sqlite 수동 설치 후 --no-* 로 재실행"; exit 1
fi
# Node/npm 최종 검증 — 여기서 못 잡으면 뒤늦게 UI 빌드(npm)에서 불명확한 오류로 터진다.
if ! have node || ! have npm; then
  echo "✋ Node.js/npm 설치 실패(네트워크/저장소 문제 가능)."
  echo "   수동 설치 후 재실행: Node 20 LTS — https://nodejs.org  또는  nvm install 20"
  exit 1
fi
say "  python=$(python3 -V 2>&1) node=$(node -v 2>&1) npm=$(npm -v 2>&1)"
PYMAJ=$(python3 -c 'import sys;print(sys.version_info[0])' 2>/dev/null||echo 0)
PYMIN=$(python3 -c 'import sys;print(sys.version_info[1])' 2>/dev/null||echo 0)
if [ "$PYMAJ" -lt 3 ] || { [ "$PYMAJ" -eq 3 ] && [ "$PYMIN" -lt 10 ]; }; then
  echo "✋ python3 $PYMAJ.$PYMIN — 3.10+ 필요(현 배포판 기본이 낮음). Ubuntu22.04+/Debian12+ 권장,"
  echo "   또는 deadsnakes PPA 등으로 python3.10+ 설치 후 재실행."; exit 1
fi

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
TUBEWAR_LAB_MONITOR=1
# 중앙 SIEM(OpenSearch+Dashboards) — 코호트 활동 lake. 미설정이면 siem_export 비활성(no-op).
# 컨테이너 기동: bash scripts/setup_siem.sh. DASHBOARDS_URL 은 저장객체(dataview) 생성용 → 로컬로 둘 것.
OPENSEARCH_URL=${OPENSEARCH_URL:-http://127.0.0.1:9210}
OPENSEARCH_DASHBOARDS_URL=${OPENSEARCH_DASHBOARDS_URL:-http://127.0.0.1:5602}
# 저장객체(dataview) ops 전용 내부 URL — 공개 터널은 saved-object API 400 → 항상 로컬.
OPENSEARCH_DASHBOARDS_INTERNAL_URL=${OPENSEARCH_DASHBOARDS_INTERNAL_URL:-http://127.0.0.1:5602}
# el34 인프라 IP 단일 노브(가변). IP 바뀌면 여기만 고치고 sync_target_ip.py 실행.
# 부트스트랩 전에 export TUBEWAR_REF_TARGET_IP=... 로 덮어쓸 수 있음.
TUBEWAR_REF_TARGET_IP=${TUBEWAR_REF_TARGET_IP:-192.168.0.80}
TUBEWAR_REF_WEB_ENTRY=${TUBEWAR_REF_WEB_ENTRY:-192.168.0.161}
TUBEWAR_REF_ATTACKER_IP=${TUBEWAR_REF_ATTACKER_IP:-192.168.0.202}
ENV
  echo "ADMIN_PW:$ADMIN_PASSWORD" > .admin-credentials.txt; chmod 600 .admin-credentials.txt
  [ "$(id -u)" -eq 0 ] && [ "$RUN_USER" != "root" ] && chown "$RUN_USER" .env .admin-credentials.txt 2>/dev/null || true
  say "  .env 생성됨 (관리자 비번 → .admin-credentials.txt)"
else
  say "  기존 .env 유지"
  API_PORT="$(grep -oP '^TUBEWAR_API_PORT=\K.*' .env || echo "$API_PORT")"
fi
AS_USER mkdir -p .data
heal_owner

# ---------- 3) python venv + 의존성 ----------
say "3/7 python venv + 의존성(apps/api[dev]) — RUN_USER=$RUN_USER 권한"
[ -d .venv ] || AS_USER python3 -m venv .venv
AS_USER .venv/bin/python -m pip install -q -U pip wheel
AS_USER .venv/bin/python -m pip install -q -e "apps/api[dev]"

# ---------- 4) UI 의존성 + 빌드 ----------
say "4/7 UI 의존성 + 빌드"
( cd apps/ui && (AS_USER npm ci 2>/dev/null || AS_USER npm install) )
if [ "$UI_MODE" = "build" ]; then ( cd apps/ui && AS_USER npm run build ); fi

# ---------- 5) DB 초기화(앱 startup이 스키마+관리자+시나리오 시드) ----------
# .env 는 app.config(pydantic-settings)가 repo root 절대경로로 직접 로드한다.
say "5/7 DB 초기화 (스키마+관리자+시나리오 자동 시드)"
AS_USER .venv/bin/python -c "
import asyncio,sys; sys.path.insert(0,'apps/api')
from app.main import lifespan, app
async def go():
    async with lifespan(app): pass
asyncio.run(go())
" && say "  DB 시드 완료: .data/tw2.sqlite3"

# 등록된 el34 인프라 vm_ip 를 .env 의 단일 노브(TUBEWAR_REF_TARGET_IP)로 정렬(멱등).
# IP 가 바뀌어도 .env 만 고치고 이 스크립트(또는 sync_target_ip.py) 재실행이면 관제가 따라간다.
AS_USER python3 scripts/sync_target_ip.py 2>/dev/null || true

# ---------- 6) 데모 학생(옵션) ----------
if [ "$DEMO_USERS" = "1" ]; then
  say "6/7 데모 학생 시드 (shin/kim/mrgrit)"
  AS_USER .venv/bin/python -c "
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
# API subprocess(채점·피드백·SIEM 분석)가 claude CLI 를 찾도록 PATH 에 사용자 로컬 bin 포함.
# systemd 기본 PATH 엔 ~/.local/bin 이 없어 shutil.which("claude")=None → AI 채점 실패했음.
RUN_HOME="$(getent passwd "$RUN_USER" | cut -d: -f6)"; RUN_HOME="${RUN_HOME:-$HOME}"
API_PATH="$RUN_HOME/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/snap/bin"
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
Environment=PATH=$API_PATH
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
  # 로그 리다이렉트도 RUN_USER 컨텍스트에서 열어 .data/*.log 가 root 소유로 남지 않게 함.
  AS_USER bash -c "cd '$REPO' && nohup .venv/bin/uvicorn app.main:app --host '$HOST' --port '$API_PORT' --app-dir apps/api > .data/api.log 2>&1 &"
  AS_USER bash -c "cd '$REPO/apps/ui' && VITE_API_TARGET='http://127.0.0.1:$API_PORT' nohup $UI_START > '$REPO/.data/ui.log' 2>&1 &"
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
