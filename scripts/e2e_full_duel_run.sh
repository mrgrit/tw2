#!/usr/bin/env bash
# e2e_full_duel.sh 를 자체 완결로 실행하기 위한 부트스트랩 러너.
# (원본 e2e_full_duel.sh 는 그대로 유지 — 실행 전 학생 가입/infra 등록 전제만 충족시킨다.)
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT=$(pwd)
PYBIN="$ROOT/.venv/bin/python"
PORT=${PORT:-9203}
BASE="http://127.0.0.1:$PORT"
DB="$ROOT/.data/e2e_fullduel.sqlite3"
rm -f "$DB"

export DATABASE_URL="sqlite+aiosqlite:///$DB"
export TUBEWAR_JWT_SECRET="e2e-secret-32-chars-please-not-shorter"
export TUBEWAR_FERNET_KEY="ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg="
export TUBEWAR_RATE_LIMIT_DISABLE=1
export TUBEWAR_GRADER_STUB=1   # e2e 결정론 채점 stub(운영 OFF)
export ADMIN_EMAIL="admin@tubewar.app"
export ADMIN_PASSWORD="Tubewar!Adm-2026"

pkill -f "uvicorn app.main:app --host 127.0.0.1 --port $PORT" 2>/dev/null || true
sleep 0.6

PIDS=()
cleanup() { for p in "${PIDS[@]:-}"; do kill "$p" 2>/dev/null || true; done; }
trap cleanup EXIT

( cd "$ROOT/apps/api" && exec "$ROOT/.venv/bin/uvicorn" app.main:app --host 127.0.0.1 --port "$PORT" ) \
  >/tmp/e2e_fullduel_api.log 2>&1 &
PIDS+=($!)
echo -n "── API health 대기"
for i in $(seq 1 40); do
  if curl -sf "$BASE/health" >/dev/null 2>&1; then echo " ok"; break; fi
  echo -n "."; sleep 0.5
  [ "$i" = "40" ] && { echo " FAIL"; tail -20 /tmp/e2e_fullduel_api.log; exit 1; }
done

# 학생 2명 가입 + infra 등록 + 사용할 시나리오 id 탐색
SCN=$(BASE="$BASE" "$PYBIN" - <<'PYEOF'
import json, os, urllib.request, urllib.error
BASE=os.environ["BASE"]
def call(p, tok=None, m="GET", b=None):
    h={"content-type":"application/json"}
    if tok: h["authorization"]="Bearer "+tok
    r=urllib.request.Request(BASE+p, method=m, headers=h, data=json.dumps(b).encode() if b is not None else None)
    try:
        with urllib.request.urlopen(r) as x: return x.status, json.loads(x.read() or b"null")
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read() or b"null")
for email,name,pw in [("alice-p8@example.com","Alice","alicepass1"),("bob-p8@example.com","Bob","bobpass123")]:
    call("/auth/signup", m="POST", b={"email":email,"password":pw,"name":name})
    _,d=call("/auth/login", m="POST", b={"email":email,"password":pw}); tok=d["access_token"]
    call("/infras", tok, "POST", {"name":name+"-6v6","vm_ip":"10.0.0.50","ssh_user":"ccc","ssh_password":"ccc","bastion_api_key":"k"})
# 듀얼용 시나리오 (red/blue 미션 다수) — bruteforce 우선, 없으면 첫 시나리오
_,d=call("/auth/login", m="POST", b={"email":"alice-p8@example.com","password":"alicepass1"}); tok=d["access_token"]
_,scns=call("/scenarios", tok)
pick=next((s for s in scns if "패스워드" in s["title"] or "WAF" in s["title"]), scns[0])
print(pick["id"])
PYEOF
)
echo "── 사용 시나리오 SCN=$SCN"

BASE="$BASE" SCN="$SCN" bash "$ROOT/scripts/e2e_full_duel.sh"
echo "═══ e2e_full_duel (bootstrap) 완료 ═══"
