#!/usr/bin/env bash
# tubewar — 1회 셋업 스크립트.
# - postgres 컨테이너 기동
# - python venv 생성 + 의존성 설치
# - npm install
set -euo pipefail
cd "$(dirname "$0")/.."

echo "[1/4] postgres 컨테이너 기동 (port 5435)"
docker compose -f infra/docker-compose.yml up -d postgres
echo "  pg ready 대기..."
for i in $(seq 1 30); do
  if docker exec tubewar-postgres pg_isready -U tubewar -d tubewar >/dev/null 2>&1; then
    echo "  ok"
    break
  fi
  sleep 1
done

echo "[2/4] python venv (.venv)"
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
. .venv/bin/activate
python -m pip install -U pip wheel >/dev/null
python -m pip install -e "apps/api[dev]"

echo "[3/4] node modules"
( cd apps/ui && npm install --silent )

echo "[4/4] .env 확인"
if [ ! -f .env ]; then
  cp .env.example .env
  echo "  .env 생성 — 필요한 값 (특히 TUBEWAR_JWT_SECRET, ADMIN_PASSWORD) 수정 후 dev 시작."
fi

cat <<'EOF'

셋업 완료. 다음:
  bash scripts/dev.sh api    # FastAPI (http://127.0.0.1:9200)
  bash scripts/dev.sh ui     # Vite   (http://127.0.0.1:5173)

DB 진입:    bash scripts/dev.sh db
테스트:     bash scripts/dev.sh test
EOF
