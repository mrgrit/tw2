"""저지 비결정성 최종 규명 — 콜드 스타트 가설.

앞선 실험에서 idx 3 은 **전체 실행의 첫 호출에서만 50**, 이후 17회는 모두 75 였다.
가설: 모델이 새로 적재된 직후(콜드)의 첫 추론과, 이미 워밍된 상태의 추론이
      수치적으로 다른 경로를 타고, 경계선 항목에서 greedy 토큰이 뒤집힌다.
검증: Ollama 의 keep_alive=0 으로 매 호출 뒤 모델을 내려 강제로 콜드 상태를 만든다.
"""
import json
import time
import urllib.request
from collections import Counter

import common  # noqa: F401
from common import JUDGE_MODEL, OLLAMA_URL
from judge import parse_score, score_prompt

data = json.load(open("test_responses.json", encoding="utf-8"))
target = data[3]


def call(prompt, keep_alive=None):
    payload = {
        "model": JUDGE_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"seed": 123, "temperature": 0, "num_ctx": 2048},
    }
    if keep_alive is not None:
        payload["keep_alive"] = keep_alive
    req = urllib.request.Request(
        OLLAMA_URL, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read())["message"]["content"]


prompt = score_prompt(target, target["model_response"])
print(f"대상: {target['instruction']}")
print(f"  정답 {target['output']!r}")
print(f"  모델 {target['model_response']!r}  (C 와 Cl — 한 글자 차이라 경계선 항목)")
print()

print("=" * 70)
print("A. 콜드 — 매 호출 직후 keep_alive=0 으로 모델을 내린다")
print("=" * 70)
cold = []
for i in range(5):
    v = parse_score(call(prompt, keep_alive=0))[0]
    cold.append(v)
    print(f"  {i+1}회: {v}   (모델 언로드 대기)")
    time.sleep(3)
print(f"  분포 {dict(Counter(cold))}")

print()
print("=" * 70)
print("B. 워밍 — 연속 호출 (모델이 적재된 채로 유지)")
print("=" * 70)
warm = []
for i in range(5):
    v = parse_score(call(prompt))[0]
    warm.append(v)
    print(f"  {i+1}회: {v}")
print(f"  분포 {dict(Counter(warm))}")

print()
print("=" * 70)
print("결론")
print("=" * 70)
cs, ws = set(cold), set(warm)
if len(cs) == 1 and len(ws) == 1 and cs != ws:
    print(f"  **가설 확정.** 콜드 상태에서는 항상 {cold[0]}, "
          f"워밍 상태에서는 항상 {warm[0]} 이다.")
    print(f"  각 상태 안에서는 완전히 결정적이고, 상태가 바뀌면 점수가 바뀐다.")
    print()
    print(f"  seed 와 temperature 를 고정해도 이 성분은 사라지지 않는다 —")
    print(f"  샘플링의 무작위성이 아니라 **서버 실행 경로의 차이**이기 때문이다.")
    print(f"  (llama.cpp 는 적재 직후와 이후의 배치 분할·KV 캐시 재사용이 달라")
    print(f"   부동소수 누적 순서가 바뀐다. 로짓 1·2등이 붙어 있는 경계선 항목에서")
    print(f"   그 미세 차이가 greedy 선택을 뒤집는다.)")
elif len(cs) == 1 and len(ws) == 1 and cs == ws:
    print(f"  콜드·워밍 모두 {cold[0]} 로 동일 — 콜드 스타트는 원인이 아니다.")
else:
    print(f"  콜드 {dict(Counter(cold))} / 워밍 {dict(Counter(warm))}")
    print(f"  단일 요인으로 설명되지 않는다. 상태 의존 성분이 있으나 "
          f"콜드/워밍 이분법으로는 부족하다.")

print()
print("  실무 의미: 저지 점수는 **±수 점의 재현 오차를 가진 측정값**이다.")
print("  '재실행하면 똑같다' 는 보장은 채점 순서·개수·서버 상태까지 동일할 때만")
print("  성립한다. 방식 A 와 B 를 비교할 때 평균 차이가 몇 점 이내라면")
print("  '같다' 고 봐야 한다.")

json.dump({"cold": cold, "warm": warm}, open("judge_coldstart.json", "w"), indent=2)
print("\n[저장] judge_coldstart.json")
