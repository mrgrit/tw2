"""V13-1 심화 — 저지 비결정성의 원인과 하한 검증의 이상치를 규명한다.

교재 P13-3 예상 결과: "temperature=0 고정 덕에 재실행해도 같은 점수가 나와야 한다."
실측: 5개 중 1개("What is the periodic symbol for chlorine?")에서 [50, 75, 75] 변동.
seed·temperature 를 고정했는데 왜 흔들리는가?
"""
import json
import statistics
from collections import Counter

import common  # noqa: F401
from common import JUDGE_MODEL
from judge import BOGUS, parse_score, query_model, score_prompt

data = json.load(open("test_responses.json", encoding="utf-8"))

print("=" * 74)
print("1. 흔들린 항목을 20회 반복 채점")
print("=" * 74)
target = next(e for e in data
              if "periodic symbol for chlorine" in e["instruction"])
print(f"지시 : {target['instruction']}")
print(f"정답 : {target['output']}")
print(f"모델 : {target['model_response']}")
print()
raws, vals = [], []
for i in range(20):
    raw = query_model(score_prompt(target, target["model_response"]))
    v, _ = parse_score(raw)
    raws.append(raw.strip())
    vals.append(v)
    print(f"  {i+1:2d}회: {v!s:>4}   원문 {raw.strip()[:60]!r}")
c = Counter(vals)
print()
print(f"  분포: {dict(c)}   고유 값 {len(c)}종")
print(f"  → 판정: {'결정적' if len(c) == 1 else '**비결정적**'}")
print(f"  저지 응답 원문의 고유 종류: {len(set(raws))}종 {set(r[:40] for r in raws)}")

print()
print("=" * 74)
print("2. 대조 — 이미 안정적이던 항목도 20회 반복")
print("=" * 74)
stable = data[0]
vals2 = []
for i in range(20):
    raw = query_model(score_prompt(stable, stable["model_response"]))
    v, _ = parse_score(raw)
    vals2.append(v)
c2 = Counter(vals2)
print(f"  지시: {stable['instruction'][:60]}")
print(f"  분포: {dict(c2)}   고유 값 {len(c2)}종")

print()
print("=" * 74)
print("3. 전체 110개를 통째로 재채점 — 1차와 몇 건이나 달라지는가")
print("=" * 74)
first = json.load(open("judge_full.json", encoding="utf-8"))["scores"]
second = []
for i, e in enumerate(data, 1):
    raw = query_model(score_prompt(e, e["model_response"]))
    v, _ = parse_score(raw)
    second.append(v)
    if i % 25 == 0:
        print(f"    {i}/110", flush=True)
diff = [(i, a, b) for i, (a, b) in enumerate(zip(first, second)) if a != b]
print()
print(f"  1차 평균 {statistics.mean(first):.2f} / 2차 평균 {statistics.mean(second):.2f}")
print(f"  점수가 달라진 항목: **{len(diff)} / 110 ({len(diff)/110*100:.1f}%)**")
for i, a, b in diff[:8]:
    print(f"    · idx {i}: {a} → {b}  ({data[i]['instruction'][:46]})")

print()
print("=" * 74)
print("4. 하한 검증의 이상치 — 엉터리 답에 95점을 준 항목")
print("=" * 74)
for i, e in enumerate(data[:10]):
    raw = query_model(score_prompt(e, BOGUS))
    v, _ = parse_score(raw)
    if v is not None and v >= 60:
        print(f"  [{v}점] idx {i}")
        print(f"    지시  : {e['instruction']}")
        print(f"    입력  : {e['input']!r}")
        print(f"    정답  : {e['output']}")
        print(f"    투입한 엉터리 응답: {BOGUS!r}")
        print(f"    저지 원문: {raw.strip()[:200]!r}")

json.dump({"chlorine_20": vals, "stable_20": vals2,
           "rescore_second": second, "n_changed": len(diff)},
          open("judge_recheck.json", "w"), indent=2)
print("\n[저장] judge_recheck.json")
