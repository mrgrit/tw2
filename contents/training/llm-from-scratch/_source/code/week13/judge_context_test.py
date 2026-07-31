"""저지 비결정성의 진짜 원인 규명 — '앞에 무엇을 채점했는가'가 점수를 바꾸는가.

관찰:
  · 같은 항목을 연속 20회 채점 → 완벽히 동일 (75 x 20)
  · 110개 시퀀스로 두 번 채점 → 9건(8.2%) 이 달라짐
즉 호출마다 무작위인 것이 아니라, **선행 요청이 남긴 서버 상태**에 좌우된다는 뜻이다.
가설: llama.cpp 의 KV 캐시 슬롯이 앞 요청의 프리픽스를 재사용하면서
      배치 분할이 달라지고, 그 미세한 수치 차이가 경계선 토큰을 뒤집는다.
검증: 같은 항목을 '선행 문맥'만 바꿔가며 채점한다.
"""
import json
from collections import Counter

import common  # noqa: F401
from judge import parse_score, query_model, score_prompt

data = json.load(open("test_responses.json", encoding="utf-8"))
TARGET_IDX = 3
target = data[TARGET_IDX]

print(f"대상 idx {TARGET_IDX}: {target['instruction']}")
print(f"  정답 {target['output']!r} / 모델 {target['model_response']!r}")
print()


def score(e, resp=None):
    raw = query_model(score_prompt(e, resp if resp is not None else e["model_response"]))
    return parse_score(raw)[0]


CONTEXTS = {
    "선행 없음 (첫 호출)": [],
    "앞에 idx 0 채점": [0],
    "앞에 idx 0,1,2 채점": [0, 1, 2],
    "앞에 idx 50 채점": [50],
    "앞에 idx 100,101,102 채점": [100, 101, 102],
    "앞에 idx 0~9 채점": list(range(10)),
}

print("=" * 74)
print("선행 문맥별 idx 3 점수 (각 문맥을 3회 반복)")
print("=" * 74)
print(f"{'선행 문맥':<26}{'1회':>6}{'2회':>6}{'3회':>6}   동일")
print("-" * 60)
results = {}
for name, pre in CONTEXTS.items():
    trio = []
    for _ in range(3):
        for j in pre:
            score(data[j])          # 선행 채점 (점수는 버린다)
        trio.append(score(target))
    results[name] = trio
    print(f"{name:<26}{trio[0]:>6}{trio[1]:>6}{trio[2]:>6}   "
          f"{'O' if len(set(trio)) == 1 else '**X**'}")

flat = [v for t in results.values() for v in t]
c = Counter(flat)
print()
print(f"전체 {len(flat)}회 중 점수 분포: {dict(c)}")
print(f"문맥별로는 항상 같은 값이 나오는가: "
      f"{all(len(set(t)) == 1 for t in results.values())}")
print(f"문맥이 다르면 값이 달라지는가: "
      f"{len({t[0] for t in results.values()}) > 1}")

print()
print("=" * 74)
print("결론")
print("=" * 74)
if len(c) > 1 and all(len(set(t)) == 1 for t in results.values()):
    print("  가설이 맞다. **같은 문맥 안에서는 완전히 결정적**이고,")
    print("  **선행 요청이 달라지면 점수가 바뀐다.**")
    print("  seed·temperature 를 고정해도 이 성분은 제거되지 않는다 —")
    print("  무작위성이 아니라 서버 측 캐시 상태의 문제이기 때문이다.")
    print()
    print("  실무 의미: '재실행하면 같은 점수' 라는 보장은 **채점 순서·개수까지")
    print("  똑같을 때만** 성립한다. 항목을 하나 추가하거나 순서를 바꾸면")
    print("  일부 점수가 달라진다. 저지 점수는 소수점까지 비교할 대상이 아니다.")
elif len(c) == 1:
    print("  이 항목은 문맥과 무관하게 안정적이다. 다른 항목으로 재시도 필요.")
else:
    print("  같은 문맥 안에서도 흔들린다 — 캐시 상태 외의 요인도 있다.")

json.dump(results, open("judge_context_test.json", "w"),
          ensure_ascii=False, indent=2)
print("\n[저장] judge_context_test.json")
