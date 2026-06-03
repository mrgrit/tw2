#!/usr/bin/env bash
# tubewar e2e — cohort 위계 + cross-infra 듀얼 + (mock) Assessor 자동 채점 + cohort 필터 리더보드.
#
# 자체 완결: mock Assessor + tubewar API(sqlite) 를 띄우고 전체 흐름을 돌린 뒤 정리한다.
# 실 6v6 Assessor 로 돌리려면 ASSESSOR_LIVE=1 + 학생 infra 의 실제 vm_ip 를 쓰도록 확장.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT=$(pwd)

PYBIN="$ROOT/.venv/bin/python"
PORT=${PORT:-9201}
MOCK_PORT=${MOCK_PORT:-9399}
BASE="http://127.0.0.1:$PORT"
DB="$ROOT/.data/e2e_cohort.sqlite3"
rm -f "$DB"

export DATABASE_URL="sqlite+aiosqlite:///$DB"
export TUBEWAR_JWT_SECRET="e2e-secret-32-chars-please-not-shorter"
export TUBEWAR_FERNET_KEY="ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg="
export TUBEWAR_RATE_LIMIT_DISABLE=1
export ADMIN_EMAIL="admin@tubewar.app"
export ADMIN_PASSWORD="Tubewar!Adm-2026"
export MOCK_ASSESS_PORT="$MOCK_PORT"

pkill -f "uvicorn app.main:app --host 127.0.0.1 --port $PORT" 2>/dev/null || true
pkill -f "mock_assessor.py" 2>/dev/null || true
sleep 0.6

PIDS=()
cleanup() { for p in "${PIDS[@]:-}"; do kill "$p" 2>/dev/null || true; done; }
trap cleanup EXIT

echo "── mock Assessor 기동 (127.0.0.1:$MOCK_PORT)"
"$PYBIN" "$ROOT/scripts/mock_assessor.py" >/tmp/e2e_mock.log 2>&1 &
PIDS+=($!)

echo "── tubewar API 기동 (sqlite, :$PORT)"
( cd "$ROOT/apps/api" && exec "$ROOT/.venv/bin/uvicorn" app.main:app --host 127.0.0.1 --port "$PORT" ) \
  >/tmp/e2e_api.log 2>&1 &
PIDS+=($!)

echo -n "── API health 대기"
for i in $(seq 1 40); do
  if curl -sf "$BASE/health" >/dev/null 2>&1; then echo " ok"; break; fi
  echo -n "."; sleep 0.5
  if [ "$i" = "40" ]; then echo " FAIL"; tail -20 /tmp/e2e_api.log; exit 1; fi
done

MOCK_PORT="$MOCK_PORT" BASE="$BASE" "$PYBIN" - <<'PYEOF'
import json, os, urllib.request, urllib.error
BASE = os.environ["BASE"]; MOCK_PORT = int(os.environ["MOCK_PORT"])

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

def login(email, pw):
    _, d = call("/auth/login", method="POST", body={"email": email, "password": pw}, expect=200)
    return d["access_token"]

def signup(email, name):
    _, d = call("/auth/signup", method="POST",
                body={"email": email, "password": "pass12345", "name": name}, expect=200)
    return d["access_token"], d["user"]["id"]

print("STEP 1. admin 로그인 + 학생 2명 가입")
atok = login("admin@tubewar.app", "Tubewar!Adm-2026")
ah = atok
red_tok, red_id = signup("red-e2e@example.com", "RedStudent")
blue_tok, blue_id = signup("blue-e2e@example.com", "BlueStudent")

print("STEP 2. 학생 infra 등록 (vm_ip=127.0.0.1, port_map.assessor=%d → mock)" % MOCK_PORT)
def reg_infra(tok, name):
    code, d = call("/infras", token=tok, method="POST", body={
        "name": name, "vm_ip": "127.0.0.1", "ssh_user": "ccc", "ssh_password": "ccc",
        "bastion_api_key": "k", "port_map": {"assessor": MOCK_PORT}})
    if code != 200: raise SystemExit(f"infra reg fail: {code} {d}")
    return d["id"]
red_inf = reg_infra(red_tok, "red-6v6")
blue_inf = reg_infra(blue_tok, "blue-6v6")
print(f"   red infra={red_inf}  blue infra={blue_inf}")

print("STEP 3. cohort 트리 생성 + 학생 배치")
_, dept = call("/cohorts", token=ah, method="POST", body={"kind": "department", "name": "정보보안과"}, expect=201)
_, grade = call("/cohorts", token=ah, method="POST", body={"kind": "grade", "name": "2학년", "parent_id": dept["id"]}, expect=201)
_, course = call("/cohorts", token=ah, method="POST", body={"kind": "course", "name": "웹해킹", "parent_id": grade["id"], "course_ref": "course3"}, expect=201)
_, section = call("/cohorts", token=ah, method="POST", body={"kind": "section", "name": "A분반", "parent_id": course["id"]}, expect=201)
call(f"/cohorts/{section['id']}/members", token=ah, method="POST", body={"user_id": red_id, "role": "student"}, expect=201)
call(f"/cohorts/{section['id']}/members", token=ah, method="POST", body={"user_id": blue_id, "role": "student"}, expect=201)
_, tree = call("/cohorts/tree", token=ah)
print(f"   트리 루트={tree[0]['name']} → ... → section={section['name']} (members 2)")

print("STEP 4. cross-infra 데모 시나리오 찾기")
_, scns = call("/scenarios", token=ah)
demo = next((s for s in scns if "cross-infra" in s["title"]), None)
if not demo: raise SystemExit("데모 시나리오 미발견 — cohort-cross-infra-demo.yaml import 확인")
print(f"   scenario #{demo['id']} {demo['title']}")

print("STEP 5. admin 이 cohort-bound 듀얼 로비 개설")
_, lob = call("/battles", token=ah, method="POST", body={
    "scenario_id": demo["id"], "mode": "duel", "monitor": "bastion",
    "cohort_id": section["id"], "participants": []}, expect=201)
bid = lob["battle"]["id"]
assert lob["battle"]["cohort_id"] == section["id"], "cohort_id 미반영"
print(f"   battle #{bid} cohort_id={lob['battle']['cohort_id']}")

print("STEP 6. red/blue join + start")
call(f"/battles/{bid}/join", token=red_tok, method="POST", body={"role": "red", "infra_id": red_inf}, expect=200)
call(f"/battles/{bid}/join", token=blue_tok, method="POST", body={"role": "blue", "infra_id": blue_inf}, expect=200)
call(f"/battles/{bid}/start", token=red_tok, method="POST", expect=200)

print("STEP 7. Assessor 자동 채점 트리거 (monitor-tick)")
_, tick = call(f"/admin/battles/{bid}/monitor-tick", token=ah, method="POST", expect=200)
print(f"   new_events={tick['new_events']}")

print("STEP 8. 채점 결과 검증 (cross-infra: red 는 상대 infra 에서 채점)")
_, det = call(f"/battles/{bid}", token=ah)
parts = {p["role"]: p for p in det["participants"]}
red_score = parts["red"]["score"]; blue_score = parts["blue"]["score"]
print(f"   RED score={red_score} (기대 35)   BLUE score={blue_score} (기대 30)")
assert red_score == 35, f"red {red_score} != 35"
assert blue_score == 30, f"blue {blue_score} != 30"

red_evs = [e for e in det["events"] if e["event_type"] == "exploit" and e["detail"].get("source") == "auto_monitor"]
assert red_evs, "red auto-monitor 이벤트 없음"
for e in red_evs:
    assert e["detail"]["assessed_infra_id"] == blue_inf, \
        f"red 미션이 상대 infra({blue_inf}) 가 아닌 {e['detail']['assessed_infra_id']} 에서 채점됨"
print(f"   ✓ red 미션 {len(red_evs)}건 모두 상대 infra #{blue_inf} 에서 Assessor 채점 (cross-infra)")
# 결정론 → LLM 0
assert all(e["detail"]["model"] == "assessor" and e["detail"]["cost_usd"] == 0.0
           for e in det["events"] if e["detail"].get("source") == "auto_monitor"), "결정론 채점인데 LLM 비용 발생"
print("   ✓ 결정론 check → LLM 호출 0 (model=assessor, cost=0)")

print("STEP 9. cohort 필터 리더보드")
_, lb = call(f"/leaderboard/users?cohort_id={course['id']}", token=ah)
names = {r["name"]: r["total_score"] for r in lb}
assert "RedStudent" in names and "BlueStudent" in names, f"cohort 리더보드 누락: {names}"
print(f"   ✓ course 서브트리 리더보드: {names}")
# admin/stats cohort 스코프
_, st = call(f"/admin/stats?cohort_id={course['id']}", token=ah)
assert st["user_count"] == 2 and st["battles_total"] == 1, f"stats 스코프 오류: {st['user_count']}/{st['battles_total']}"
print(f"   ✓ cohort stats: user_count={st['user_count']} battles_total={st['battles_total']}")

print("STEP 10. 실습 모니터링 (/activity pull → 진도·병목) + 피드백")
_, tick2 = call(f"/monitoring/battles/{bid}/lab-tick?with_feedback=true", token=ah, method="POST", expect=200)
print(f"   lab-tick ingested={tick2['ingested']} students={tick2['students']} stuck={tick2['stuck']}")
assert tick2["ingested"] > 0, "활동 미적재"
_, prog = call(f"/monitoring/battles/{bid}/progress", token=ah)
print(f"   진도: " + ", ".join(f"{s['name']}={s['completion']}%{'(막힘)' if s['stuck'] else ''}" for s in prog["students"]))
_, tl = call(f"/monitoring/battles/{bid}/activity?user_id={red_id}", token=ah)
assert len(tl) > 0, "타임라인 비어있음"
print(f"   ✓ red 타임라인 {len(tl)}건 (명령/FIM/알림)")

# 병목 학생에게 자동 피드백 생성됐는지 + 강사 on-demand 피드백
_, fbs = call(f"/feedback?user_id={red_id}", token=ah)
if not fbs:
    call(f"/feedback/students/{red_id}", token=ah, method="POST",
         body={"battle_id": bid, "delivered_to": "both"}, expect=201)
    _, fbs = call(f"/feedback?user_id={red_id}", token=ah)
assert fbs, "피드백 미생성"
print(f"   ✓ 피드백 {len(fbs)}건 (model={fbs[0]['model']}, trigger={fbs[0]['trigger']})")
# 학생 본인 열람
_, mine = call("/feedback/me", token=red_tok)
assert any(f["id"] == fbs[0]["id"] for f in mine if fbs[0]["delivered_to"] in ("student", "both")) or mine
print(f"   ✓ 학생 본인 피드백 열람 {len(mine)}건")

# 중앙 SIEM 딥링크/프로비저닝 (OPENSEARCH 미설정 → disabled no-op)
_, siem = call(f"/monitoring/cohorts/{course['id']}/siem", token=ah)
print(f"   ✓ SIEM: enabled={siem['enabled']} cohort_path={siem['cohort_path']}")

call(f"/battles/{bid}/end", token=red_tok, method="POST", expect=200)
print("\n✓✓✓ cohort cross-infra e2e 통과 — battle #%d" % bid)
PYEOF

echo "═══ e2e_cohort_cross_infra 완료 ═══"
