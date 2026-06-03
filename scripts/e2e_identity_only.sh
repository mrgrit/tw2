#!/usr/bin/env bash
# tubewar e2e — 신원-only 모드 (cohort 없이 solo/duel 정상 동작).
# cohort_id=null 경로가 회귀 없이 작동함을 증명한다. 자체 완결(sqlite API 기동).
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT=$(pwd)

PYBIN="$ROOT/.venv/bin/python"
PORT=${PORT:-9202}
BASE="http://127.0.0.1:$PORT"
DB="$ROOT/.data/e2e_identity.sqlite3"
rm -f "$DB"

export DATABASE_URL="sqlite+aiosqlite:///$DB"
export TUBEWAR_JWT_SECRET="e2e-secret-32-chars-please-not-shorter"
export TUBEWAR_FERNET_KEY="ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg="
export TUBEWAR_RATE_LIMIT_DISABLE=1
export ADMIN_EMAIL="admin@tubewar.app"
export ADMIN_PASSWORD="Tubewar!Adm-2026"

pkill -f "uvicorn app.main:app --host 127.0.0.1 --port $PORT" 2>/dev/null || true
sleep 0.6

PIDS=()
cleanup() { for p in "${PIDS[@]:-}"; do kill "$p" 2>/dev/null || true; done; }
trap cleanup EXIT

echo "── tubewar API 기동 (sqlite, :$PORT)"
( cd "$ROOT/apps/api" && exec "$ROOT/.venv/bin/uvicorn" app.main:app --host 127.0.0.1 --port "$PORT" ) \
  >/tmp/e2e_identity_api.log 2>&1 &
PIDS+=($!)

echo -n "── API health 대기"
for i in $(seq 1 40); do
  if curl -sf "$BASE/health" >/dev/null 2>&1; then echo " ok"; break; fi
  echo -n "."; sleep 0.5
  if [ "$i" = "40" ]; then echo " FAIL"; tail -20 /tmp/e2e_identity_api.log; exit 1; fi
done

BASE="$BASE" "$PYBIN" - <<'PYEOF'
import json, os, urllib.request, urllib.error
BASE = os.environ["BASE"]

def call(path, *, token=None, method="GET", body=None, expect=None):
    headers = {"content-type": "application/json"}
    if token: headers["authorization"] = "Bearer " + token
    req = urllib.request.Request(BASE + path, method=method, headers=headers,
                                 data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req) as r:
            data = json.loads(r.read() or b"null"); code = r.status
    except urllib.error.HTTPError as e:
        data = json.loads(e.read() or b"null"); code = e.code
    if expect and code != expect:
        raise SystemExit(f"FAIL {method} {path}: {code} {data}")
    return code, data

def signup(email, name):
    _, d = call("/auth/signup", method="POST",
                body={"email": email, "password": "pass12345", "name": name}, expect=200)
    return d["access_token"], d["user"]["id"]

print("STEP 1. 학생 가입 + infra 등록")
tok, uid = signup("solo-e2e@example.com", "Solo")
call("/infras", token=tok, method="POST", body={
    "name": "solo-6v6", "vm_ip": "10.0.0.9", "ssh_user": "ccc",
    "ssh_password": "ccc", "bastion_api_key": "k"}, expect=200)
_, infras = call("/infras", token=tok)
inf = infras[0]["id"]

print("STEP 2. cohort 없이 solo battle 생성/시작 (신원-only)")
_, scns = call("/scenarios", token=tok)
sid = scns[0]["id"]
_, cr = call("/battles", token=tok, method="POST", body={
    "scenario_id": sid, "mode": "solo", "monitor": "bastion",
    "participants": [{"user_id": uid, "role": "solo", "infra_id": inf}]}, expect=201)
bid = cr["battle"]["id"]
assert cr["battle"]["cohort_id"] is None, "신원-only 인데 cohort_id 가 채워짐"
print(f"   battle #{bid} cohort_id={cr['battle']['cohort_id']} (null=신원-only)")
call(f"/battles/{bid}/start", token=tok, method="POST", expect=200)

print("STEP 3. 수동 이벤트 보고 → 점수")
call(f"/battles/{bid}/events", token=tok, method="POST", body={
    "event_type": "exploit", "target": "web", "description": "SQLi 성공", "points": 25}, expect=201)
_, det = call(f"/battles/{bid}", token=tok)
score = det["participants"][0]["score"]
assert score == 25, f"score {score} != 25"
print(f"   ✓ solo score={score}")
call(f"/battles/{bid}/end", token=tok, method="POST", expect=200)

print("STEP 4. cohort 없는 리더보드(전체) 에 반영")
_, lb = call("/leaderboard/users", token=tok)
assert any(r["name"] == "Solo" and r["total_score"] == 25 for r in lb), f"리더보드 누락: {lb}"
print("   ✓ 무필터 리더보드에 신원-only 학생 반영")

print("\n✓✓✓ identity-only e2e 통과 — battle #%d" % bid)
PYEOF

echo "═══ e2e_identity_only 완료 ═══"
