#!/usr/bin/env bash
# tubewar — 개발 명령 dispatcher.
set -euo pipefail
cd "$(dirname "$0")/.."

cmd="${1:-help}"

case "$cmd" in
  api)
    . .venv/bin/activate
    set -a; [ -f .env ] && . ./.env; set +a
    cd apps/api
    exec uvicorn app.main:app --host "${TUBEWAR_API_HOST:-0.0.0.0}" \
      --port "${TUBEWAR_API_PORT:-9200}" --reload --reload-dir app
    ;;
  ui)
    cd apps/ui
    exec npm run dev
    ;;
  build-ui)
    cd apps/ui
    exec npm run build
    ;;
  db)
    exec docker exec -it tubewar-postgres psql -U tubewar -d tubewar
    ;;
  pg-up)
    exec docker compose -f infra/docker-compose.yml up -d postgres
    ;;
  pg-down)
    exec docker compose -f infra/docker-compose.yml down
    ;;
  test)
    . .venv/bin/activate
    set -a; [ -f .env ] && . ./.env; set +a
    exec python -m pytest tests/ -v
    ;;
  help|*)
    cat <<'EOF'
tubewar dev commands:
  bash scripts/dev.sh api       # FastAPI dev server (autoreload)
  bash scripts/dev.sh ui        # Vite dev server
  bash scripts/dev.sh build-ui  # Production UI build
  bash scripts/dev.sh db        # psql 진입
  bash scripts/dev.sh pg-up     # postgres 컨테이너 기동
  bash scripts/dev.sh pg-down   # postgres 컨테이너 정지
  bash scripts/dev.sh test      # pytest
EOF
    ;;
esac
