#!/bin/bash
# tubewar Phase 9.2 — 1:1 duel 풀 미션 e2e
#
# 흐름: admin 이 로비 개설 → alice (red) + bob (blue) self-join → start →
#       시나리오의 모든 RED/BLUE 미션을 매뉴얼 보고 → 점수/근거/힌트/리더보드 검증.
#
# 환경 변수 (선택):
#   BASE          tubewar API base URL                   (default http://127.0.0.1:9200)
#   ADMIN_EMAIL / ADMIN_PW
#   RED_EMAIL  / RED_PW   (사전 회원가입 + infra 등록 필요)
#   BLUE_EMAIL / BLUE_PW
#   SCN           시나리오 id                            (default 4 — 패스워드 공격, 6+6 미션)
#
set -euo pipefail
export PYTHONIOENCODING=utf-8
export LC_ALL=C.UTF-8

BASE=${BASE:-http://127.0.0.1:9200}
ADMIN_EMAIL=${ADMIN_EMAIL:-admin@tubewar.app}
ADMIN_PW=${ADMIN_PW:-Tubewar!Adm-2026}
RED_EMAIL=${RED_EMAIL:-alice-p8@example.com}
RED_PW=${RED_PW:-alicepass1}
BLUE_EMAIL=${BLUE_EMAIL:-bob-p8@example.com}
BLUE_PW=${BLUE_PW:-bobpass123}
SCN=${SCN:-4}

JQ() { python3 -c "import json,sys; d=json.loads(sys.stdin.read()); print($1)"; }

login() {
  curl -sf -X POST $BASE/auth/login -H 'content-type: application/json' \
    -d "{\"email\":\"$1\",\"password\":\"$2\"}" | JQ "d['access_token']"
}
me_id()       { curl -sf $BASE/auth/me  -H "authorization: Bearer $1" | JQ "d['id']"; }
first_infra() { curl -sf $BASE/infras   -H "authorization: Bearer $1" | JQ "d[0]['id'] if d else 0"; }

ADM_TOK=$(login "$ADMIN_EMAIL" "$ADMIN_PW")
ALICE_TOK=$(login "$RED_EMAIL" "$RED_PW")
BOB_TOK=$(login "$BLUE_EMAIL" "$BLUE_PW")
ALICE=$(me_id "$ALICE_TOK")
BOB=$(me_id "$BOB_TOK")
INFRA_A=$(first_infra "$ALICE_TOK")
INFRA_B=$(first_infra "$BOB_TOK")

echo "  alice user=$ALICE infra=$INFRA_A | bob user=$BOB infra=$INFRA_B | scenario=$SCN"
test "$INFRA_A" != "0" -a "$INFRA_B" != "0" \
  || { echo "FATAL: 학생 인프라 미등록 — /myinfra 에서 등록 후 재실행"; exit 1; }

echo "═══════════════════════════════════════════════════════════"
echo " STEP 1. admin 이 로비 개설 (duel, juiceshop+dvwa, hint=on)"
echo "═══════════════════════════════════════════════════════════"
LOB=$(curl -sf -X POST $BASE/battles -H "authorization: Bearer $ADM_TOK" \
  -H 'content-type: application/json' \
  -d "{\"scenario_id\":$SCN,\"mode\":\"duel\",\"monitor\":\"bastion\",\"hint_enabled\":true,\"target_apps\":[\"juiceshop\",\"dvwa\"],\"participants\":[]}")
BID=$(echo "$LOB" | JQ "d['battle']['id']")
echo "  ✓ battle_id=$BID, 참가자=$(echo "$LOB" | JQ "len(d['participants'])") (lobby)"

echo
echo "═══════════════════════════════════════════════════════════"
echo " STEP 2. admin 이 start 시도 → 400 (참가자 없음)"
echo "═══════════════════════════════════════════════════════════"
RC=$(curl -s -o /tmp/e2e_err -w '%{http_code}' -X POST $BASE/battles/$BID/start \
  -H "authorization: Bearer $ADM_TOK")
echo "  HTTP=$RC body=$(cat /tmp/e2e_err)"

echo
echo "═══════════════════════════════════════════════════════════"
echo " STEP 3. alice red join + bob blue join"
echo "═══════════════════════════════════════════════════════════"
curl -sf -X POST $BASE/battles/$BID/join -H "authorization: Bearer $ALICE_TOK" \
  -H 'content-type: application/json' \
  -d "{\"role\":\"red\",\"infra_id\":$INFRA_A}" \
  | JQ "f\"  ✓ alice my_role={d['my_role']}, my_missions={len(d['my_missions'])}\""
curl -sf -X POST $BASE/battles/$BID/join -H "authorization: Bearer $BOB_TOK" \
  -H 'content-type: application/json' \
  -d "{\"role\":\"blue\",\"infra_id\":$INFRA_B}" \
  | JQ "f\"  ✓ bob   my_role={d['my_role']}, my_missions={len(d['my_missions'])}\""

echo
echo "═══════════════════════════════════════════════════════════"
echo " STEP 4. 중복 join 거부 (alice 재시도)"
echo "═══════════════════════════════════════════════════════════"
RC=$(curl -s -o /tmp/e2e_err -w '%{http_code}' -X POST $BASE/battles/$BID/join \
  -H "authorization: Bearer $ALICE_TOK" -H 'content-type: application/json' \
  -d "{\"role\":\"blue\",\"infra_id\":$INFRA_A}")
echo "  HTTP=$RC body=$(cat /tmp/e2e_err)"

echo
echo "═══════════════════════════════════════════════════════════"
echo " STEP 5. alice 시점 — RED 미션 6개 brief"
echo "═══════════════════════════════════════════════════════════"
curl -sf $BASE/battles/$BID -H "authorization: Bearer $ALICE_TOK" \
  | python3 -c "
import json, sys
d=json.loads(sys.stdin.read())
print(f'  my_role={d[\"my_role\"]}, my_missions={len(d[\"my_missions\"])} 개')
for m in d['my_missions']:
    print(f'    🔴 #{m[\"order\"]:>2} +{m[\"points\"]:>2}점 [{m[\"target_vm\"] or \"-\":>10}] {m[\"instruction\"][:80]}')"

echo
echo "═══════════════════════════════════════════════════════════"
echo " STEP 6. start"
echo "═══════════════════════════════════════════════════════════"
curl -sf -X POST $BASE/battles/$BID/start -H "authorization: Bearer $ALICE_TOK" \
  | JQ "f\"  ✓ status={d['battle']['status']}\""

# 미션 데이터 fetch + 이벤트 보고를 python 으로 처리 (한글 안전)
echo
echo "═══════════════════════════════════════════════════════════"
echo " STEP 7+8. RED 6 미션 (alice) + BLUE 6 미션 (bob) 모두 보고"
echo "═══════════════════════════════════════════════════════════"
python3 - <<PYEOF
import json, urllib.request, urllib.error

BASE = "$BASE"
BID = $BID
ALICE_TOK = "$ALICE_TOK"
BOB_TOK = "$BOB_TOK"

def call(path, *, token, method="GET", body=None):
    req = urllib.request.Request(
        BASE + path, method=method,
        headers={"authorization": "Bearer " + token, "content-type": "application/json"},
        data=json.dumps(body).encode("utf-8") if body else None,
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())

# 미션 fetch — alice 시점이면 my=red, opp=blue
detail_a = call(f"/battles/{BID}", token=ALICE_TOK)
detail_b = call(f"/battles/{BID}", token=BOB_TOK)
red_missions = [m for m in detail_a["my_missions"] if m["side"] == "red"]
blue_missions = [m for m in detail_b["my_missions"] if m["side"] == "blue"]
print(f"  RED missions={len(red_missions)} BLUE missions={len(blue_missions)}")

red_total = blue_total = 0

# RED — alice 보고
print("  ── RED 보고 (alice) ──")
for m in sorted(red_missions, key=lambda x: x["order"]):
    ev = call(f"/battles/{BID}/events", token=ALICE_TOK, method="POST", body={
        "event_type": "exploit",
        "target": m["target_vm"] or "attacker",
        "description": f"미션 #{m['order']} 완료 — {m['instruction'][:90]}",
        "points": m["points"],
        "mission_order": m["order"], "mission_side": "red",
        "what_i_did": f"미션 #{m['order']} 수행: {m['instruction'][:120]}",
        "what_happened": "성공",
    })
    red_total += m["points"]
    print(f"    ✓ RED #{m['order']:>2} (+{m['points']:>2}) → 누적 {red_total}")

# BLUE — bob 보고
print("  ── BLUE 보고 (bob) ──")
for m in sorted(blue_missions, key=lambda x: x["order"]):
    et = "detect" if m["order"] <= 2 else ("block" if m["order"] <= 4 else "alert")
    ev = call(f"/battles/{BID}/events", token=BOB_TOK, method="POST", body={
        "event_type": et,
        "target": m["target_vm"] or "siem",
        "description": f"방어 미션 #{m['order']} 완료 — {m['instruction'][:90]}",
        "points": m["points"],
        "mission_order": m["order"], "mission_side": "blue",
        "what_i_did": f"방어 미션 #{m['order']} 수행: {m['instruction'][:120]}",
        "what_happened": "완료",
    })
    blue_total += m["points"]
    print(f"    ✓ BLUE #{m['order']:>2} {et:>6} (+{m['points']:>2}) → 누적 {blue_total}")

# 검증
print()
print("  ── 점수 검증 ──")
detail = call(f"/battles/{BID}", token=ALICE_TOK)
red_score = next((p["score"] for p in detail["participants"] if p["role"] == "red"), 0)
blue_score = next((p["score"] for p in detail["participants"] if p["role"] == "blue"), 0)
print(f"  RED  실제={red_score} 기대={red_total} {'✓' if red_score == red_total else '✗'}")
print(f"  BLUE 실제={blue_score} 기대={blue_total} {'✓' if blue_score == blue_total else '✗'}")
print(f"  events={len(detail['events'])}")

# 매뉴얼 이벤트의 자연어 reasoning 1건 sample
sample = next((e for e in detail["events"] if e["event_type"] == "exploit"), None)
if sample and sample.get("reasoning"):
    print()
    print("  ── 매뉴얼 RED 이벤트 reasoning 샘플 ──")
    for line in sample["reasoning"].splitlines()[:6]:
        print(f"    {line}")

# 힌트
print()
print("  ── alice 힌트 요청 (bastion 모드 = 무료) ──")
hint = call(f"/battles/{BID}/hint", token=ALICE_TOK, method="POST",
            body={"mission_side": "red", "note": "전 미션 다 했는데 더 할 게 있나?"})
print(f"    model={hint['model']} cache={hint['cache_hit']} cost=\${hint['cost_usd']:.4f}")
for line in hint["text"].splitlines()[:6]:
    print(f"    {line}")
PYEOF

echo
echo "═══════════════════════════════════════════════════════════"
echo " STEP 9. 종료 + leaderboard 반영"
echo "═══════════════════════════════════════════════════════════"
curl -sf -X POST $BASE/battles/$BID/end -H "authorization: Bearer $ALICE_TOK" \
  | JQ "f\"  ✓ status={d['battle']['status']}\""

curl -sf "$BASE/leaderboard/battles/$BID" -H "authorization: Bearer $ALICE_TOK" \
  | python3 -c "
import json, sys
d=json.loads(sys.stdin.read())
print(f'  battle #{d[\"battle_id\"]} ({d.get(\"scenario_title\",\"\")[:30]}) status={d[\"status\"]}')
for r in d['rows']:
    print(f'    rank #{r[\"rank\"]} {r[\"role_in_battle\"]:>4} {r[\"name\"]:>10} score={r[\"score\"]:>3} (red_evt={r[\"events_red\"]}, blue_evt={r[\"events_blue\"]})')"

curl -sf "$BASE/leaderboard/users" -H "authorization: Bearer $ALICE_TOK" \
  | python3 -c "
import json, sys
d=json.loads(sys.stdin.read())
print('  /leaderboard/users top 5:')
for r in d[:5]:
    print(f'    {r[\"name\"]:>12} battles={r[\"battle_count\"]:>2} wins={r[\"win_count\"]:>2} total={r[\"total_score\"]:>4} avg={r[\"avg_score\"]}')"

echo
echo "═══════════════════════════════════════════════════════════"
echo " ✓✓✓ Phase 9.2 1:1 duel 풀 미션 e2e 완료 — battle_id=$BID"
echo "═══════════════════════════════════════════════════════════"
