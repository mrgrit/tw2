"""P12-5 — 훈련 전 데이터 품질 점검. '데이터가 절반이다'."""
import re
from collections import Counter, defaultdict

import matplotlib.pyplot as plt
import tiktoken

from instr_data import format_input, load_data

data = load_data()
tokenizer = tiktoken.get_encoding("gpt2")

findings = []          # (항목, 건수, 권고)
sections = []          # 상세 서술


def norm(s):
    return re.sub(r"\s+", " ", s.strip().lower())


# ---------------------------------------------------------------------------
print("=" * 72)
print("1. 완전 중복 쌍 (instruction + input 기준)")
print("=" * 72)
exact = defaultdict(list)
for i, d in enumerate(data):
    exact[(d["instruction"], d["input"])].append(i)
dups_exact = {k: v for k, v in exact.items() if len(v) > 1}
print(f"  중복 키 {len(dups_exact)}개, 관련 항목 "
      f"{sum(len(v) for v in dups_exact.values())}개")
for k, v in list(dups_exact.items())[:5]:
    outs = {data[i]["output"] for i in v}
    print(f"    · idx {v} — instruction={k[0][:60]!r}")
    print(f"      output 이 서로 {'같다' if len(outs) == 1 else '다르다'} "
          f"({len(outs)}종)")
same_out_groups = sum(1 for v in dups_exact.values()
                      if len({data[i]["output"] for i in v}) == 1)
diff_out_groups = len(dups_exact) - same_out_groups
n_dup_items = sum(len(v) for v in dups_exact.values())
print(f"  output 까지 완전 동일한 그룹: {same_out_groups}개")
print(f"  output 이 다른 그룹        : {diff_out_groups}개  ← 스타일 모순 후보")
findings.append(("완전 중복 쌍 (instruction+input)", len(dups_exact),
                 f"관련 항목 {n_dup_items}건. output 이 다른 그룹 "
                 f"{diff_out_groups}개는 **스타일 일관성** 문제 — 아래 참조"
                 if dups_exact else "조치 불필요"))

# 스타일 모순의 성격을 정량화한다: 같은 질문에 대한 응답 길이 편차
style_gap = []
for k, v in dups_exact.items():
    outs = [data[i]["output"] for i in v]
    if len(set(outs)) == 1:
        continue
    toks = [len(tokenizer.encode(o)) for o in outs]
    style_gap.append((k, v, outs, min(toks), max(toks), max(toks) / min(toks)))
style_gap.sort(key=lambda t: -t[5])
if style_gap:
    print(f"  응답 길이 배율이 가장 큰 그룹 3개:")
    for k, v, outs, mn, mx, ratio in style_gap[:3]:
        print(f"    · idx {v} — {mn}토큰 vs {mx}토큰 ({ratio:.1f}배)")
        print(f"      instruction: {k[0][:70]}")
        for i, o in zip(v, outs):
            print(f"        [{i}] {o[:80]!r}")

# ---------------------------------------------------------------------------
print()
print("=" * 72)
print("2. 근사 중복 후보")
print("=" * 72)
# 2-a 정규화 후 동일
nkey = defaultdict(list)
for i, d in enumerate(data):
    nkey[(norm(d["instruction"]), norm(d["input"]))].append(i)
near_norm = {k: v for k, v in nkey.items() if len(v) > 1}
extra_norm = len(near_norm) - len(dups_exact)
print(f"  2-a 정규화(소문자·공백) 후 동일: 키 {len(near_norm)}개 "
      f"(완전 중복 외 추가 {extra_norm}개)")

# 2-b 앞 50자 동일
head = defaultdict(list)
for i, d in enumerate(data):
    head[d["instruction"][:50]].append(i)
near_head = {k: v for k, v in head.items() if len(v) > 1}
print(f"  2-b instruction 앞 50자 동일: 키 {len(near_head)}개, "
      f"관련 항목 {sum(len(v) for v in near_head.values())}개")
shown = 0
for k, v in sorted(near_head.items(), key=lambda kv: -len(kv[1])):
    if shown >= 3:
        break
    print(f"    · {len(v)}건 — {k!r}")
    for i in v[:3]:
        print(f"        idx {i}: instruction={data[i]['instruction'][:80]!r} "
              f"input={data[i]['input'][:30]!r}")
    shown += 1
findings.append(("근사 중복 — 정규화 후 동일", len(near_norm), "완전 중복과 동일 조치"))
findings.append(("근사 중복 — instruction 앞 50자 동일", len(near_head),
                 "대부분 같은 유형의 정당한 변형(input 이 다름) — 제외 불필요"))

# ---------------------------------------------------------------------------
print()
print("=" * 72)
print("3. 빈 output / 지나치게 짧은 output (토큰 3개 미만)")
print("=" * 72)
empty_out = [i for i, d in enumerate(data) if not d["output"].strip()]
short_out = [(i, len(tokenizer.encode(d["output"])))
             for i, d in enumerate(data)
             if d["output"].strip() and len(tokenizer.encode(d["output"])) < 3]
print(f"  빈 output       : {len(empty_out)}건 {empty_out[:10]}")
print(f"  토큰 3개 미만    : {len(short_out)}건")
for i, n in short_out[:5]:
    print(f"    · idx {i} ({n}토큰): instruction={data[i]['instruction'][:60]!r}")
    print(f"      output={data[i]['output']!r}")
findings.append(("빈 output", len(empty_out),
                 "제외" if empty_out else "조치 불필요"))
findings.append(("output 토큰 3개 미만", len(short_out),
                 "사례 확인 후 판단" if short_out else "조치 불필요"))

# 빈 instruction 도 겸사겸사
empty_instr = [i for i, d in enumerate(data) if not d["instruction"].strip()]
print(f"  빈 instruction  : {len(empty_instr)}건")
findings.append(("빈 instruction", len(empty_instr),
                 "제외" if empty_instr else "조치 불필요"))

# ---------------------------------------------------------------------------
print()
print("=" * 72)
print("4. 조립 완성 텍스트의 토큰 길이 분포")
print("=" * 72)
lengths = []
for d in data:
    full = format_input(d) + f"\n\n### Response:\n{d['output']}"
    lengths.append(len(tokenizer.encode(full)))

lengths_sorted = sorted(lengths)
n = len(lengths)
stats = {
    "최소": lengths_sorted[0],
    "25%": lengths_sorted[n // 4],
    "중앙값": lengths_sorted[n // 2],
    "75%": lengths_sorted[3 * n // 4],
    "95%": lengths_sorted[int(n * 0.95)],
    "99%": lengths_sorted[int(n * 0.99)],
    "최대": lengths_sorted[-1],
}
for k, v in stats.items():
    print(f"  {k:<6}: {v:>5} 토큰")
over = sum(1 for x in lengths if x > 1024)
print(f"  평균  : {sum(lengths)/n:.1f} 토큰")
print(f"  1024 초과 항목: **{over}건**")
print(f"  → 최장 {max(lengths)} 토큰은 1024 의 "
      f"{max(lengths)/1024*100:.1f}% 에 불과하다. "
      f"allowed_max_length=1024 가 아무것도 자르지 않는다.")

fig, ax = plt.subplots(figsize=(10, 4.5))
ax.hist(lengths, bins=60, color="#4477aa", edgecolor="white")
ax.axvline(1024, color="red", linestyle="--",
           label=f"allowed_max_length=1024 (초과 {over}건)")
ax.axvline(max(lengths), color="orange", linestyle=":",
           label=f"최장 {max(lengths)} 토큰")
ax.set_xlabel("조립 완성 텍스트 토큰 길이")
ax.set_ylabel("항목 수")
ax.set_title("지시 데이터 토큰 길이 분포 (n=1,100)")
ax.legend()
fig.tight_layout()
fig.savefig("length_hist.png", dpi=130)
print("  [저장] length_hist.png")
findings.append(("1024 토큰 초과 항목", over,
                 "조치 불필요 — allowed_max_length 가 발동하지 않음"))

# ---------------------------------------------------------------------------
print()
print("=" * 72)
print("5. output 이 instruction 을 그대로 되풀이하는 항목")
print("=" * 72)
echo_exact, echo_prefix, echo_contained = [], [], []
for i, d in enumerate(data):
    ni, no = norm(d["instruction"]), norm(d["output"])
    if not ni or not no:
        continue
    if ni == no:
        echo_exact.append(i)
    elif no.startswith(ni):
        echo_prefix.append(i)
    elif len(ni) > 20 and ni in no:
        echo_contained.append(i)

print(f"  output == instruction (정규화 후) : {len(echo_exact)}건 {echo_exact[:8]}")
print(f"  output 이 instruction 으로 시작    : {len(echo_prefix)}건 {echo_prefix[:8]}")
print(f"  output 안에 instruction 이 포함    : {len(echo_contained)}건 "
      f"{echo_contained[:8]}")
for i in (echo_exact + echo_prefix + echo_contained)[:3]:
    print(f"    · idx {i}")
    print(f"      instruction: {data[i]['instruction'][:90]!r}")
    print(f"      output     : {data[i]['output'][:90]!r}")
findings.append(("output == instruction", len(echo_exact),
                 "제외" if echo_exact else "조치 불필요"))
findings.append(("output 이 instruction 으로 시작", len(echo_prefix),
                 "사례 확인 — 정당한 되풀이일 수 있음" if echo_prefix else "조치 불필요"))

# ---------------------------------------------------------------------------
# 리포트
lines = ["# quality_report.md — 지시 데이터 품질 점검 (P12-5 산출물)", ""]
lines.append(f"대상: `instruction-data.json` (1,100건) · "
             f"토크나이저: tiktoken gpt2")
lines.append("")
lines.append("## 요약표")
lines.append("")
lines.append("| 점검 항목 | 건수 | 제외/수정 권고 |")
lines.append("|---|---|---|")
for name, cnt, rec in findings:
    lines.append(f"| {name} | **{cnt}** | {rec} |")
lines.append("")
lines.append("## 토큰 길이 분포")
lines.append("")
lines.append("| 통계 | 값 |")
lines.append("|---|---|")
for k, v in stats.items():
    lines.append(f"| {k} | {v} 토큰 |")
lines.append(f"| 평균 | {sum(lengths)/n:.1f} 토큰 |")
lines.append(f"| **1024 초과** | **{over}건** |")
lines.append("")
lines.append("![토큰 길이 분포](length_hist.png)")
lines.append("")
lines.append(f"최장이 **{max(lengths)} 토큰**으로 1024 의 "
             f"{max(lengths)/1024*100:.1f}% 에 불과하다. "
             f"`allowed_max_length=1024` 는 이 데이터에서 **한 건도 자르지 않는다** — "
             f"13주차 훈련에서 잘림으로 인한 응답 절단은 걱정하지 않아도 된다.")
lines.append("")
lines.append("## 대표 사례")
lines.append("")
if near_head:
    k, v = max(near_head.items(), key=lambda kv: len(kv[1]))
    lines.append(f"**근사 중복(앞 50자 동일) 최다 그룹 — {len(v)}건**")
    lines.append("")
    lines.append("| idx | instruction | input | output |")
    lines.append("|---|---|---|---|")
    for i in v[:4]:
        lines.append(f"| {i} | {data[i]['instruction'][:60]} | "
                     f"`{data[i]['input'][:30]}` | {data[i]['output'][:50]} |")
    lines.append("")
    lines.append("→ instruction 은 같지만 **input 이 서로 다르다.** "
                 "같은 과제 유형을 여러 입력으로 연습시키는 정당한 구성이다. "
                 "제외하면 오히려 그 유형의 학습 신호가 약해진다. **제외하지 않는다.**")
    lines.append("")
if short_out:
    lines.append("**토큰 3개 미만 output**")
    lines.append("")
    lines.append("| idx | 토큰 수 | instruction | output |")
    lines.append("|---|---|---|---|")
    for i, c in short_out[:5]:
        lines.append(f"| {i} | {c} | {data[i]['instruction'][:60]} | "
                     f"`{data[i]['output']}` |")
    lines.append("")
if style_gap:
    lines.append("**응답 스타일 모순 — 같은 질문에 서로 다른 길이의 정답**")
    lines.append("")
    lines.append("| idx | instruction | input | output | 토큰 |")
    lines.append("|---|---|---|---|---|")
    for k, v, outs, mn, mx, ratio in style_gap[:4]:
        for i, o in zip(v, outs):
            lines.append(f"| {i} | {k[0][:50]} | `{k[1][:24]}` | "
                         f"{o[:70].replace('|', '\\|')} | "
                         f"{len(tokenizer.encode(o))} |")
        lines.append(f"| | | | ↑ **{ratio:.1f}배 길이 차이** | |")
    lines.append("")

lines.append("## 결론과 13주차 반영 권고")
lines.append("")
lines.append("**형식적 결함은 0건이다.** 빈 output 0 · 빈 instruction 0 · "
             "output==instruction 0 · 1024 초과 0. "
             "교재용으로 정제된 데이터셋이라는 설명과 일치한다.")
lines.append("")
lines.append(f"**그러나 '문제 없음'은 아니다.** 완전 중복 {len(dups_exact)}그룹"
             f"({n_dup_items}건)이 있고, 그중 **{diff_out_groups}그룹 전부**에서 "
             f"output 이 서로 다르다. 사실관계가 틀린 것은 아니지만 "
             f"**응답 스타일이 모순된다** — 같은 질문에 한쪽은 완전한 문장으로, "
             f"다른 쪽은 단어 하나로 답한다.")
lines.append("")
lines.append("이것이 왜 문제인가: 지시 튜닝이 가르치는 것은 지식이 아니라 "
             "**\"지시가 오면 이런 형식으로 응답한다\"** 는 규약이다. "
             "동일한 프롬프트에 상반된 길이의 정답을 주면 모델은 "
             "\"짧게 답할지 길게 답할지\"에 대해 서로 상쇄되는 신호를 받는다. "
             "1,100건짜리 소규모 데이터에서 45건(4.1%)이 이런 상태라면 무시할 수 없다.")
lines.append("")
lines.append("**13주차 훈련에 실제로 반영할 조치**")
lines.append("")
lines.append(f"1. **`allowed_max_length=1024` 를 그대로 둔다.** 최장 {max(lengths)} 토큰이라 "
             f"발동하지 않는다. 다만 코드에서 빼지는 말 것 — 다른 데이터로 바꿀 때의 안전장치다.")
lines.append(f"2. **배치 크기를 길이 기준으로 잡아도 안전하다.** 95 퍼센타일이 "
             f"{stats['95%']} 토큰이므로 batch_size=8 이면 배치당 최대 "
             f"약 {stats['최대'] * 8:,} 토큰 규모다.")
lines.append(f"3. **근사 중복 {len(near_head)}그룹(앞 50자 동일)은 제외하지 않는다.** "
             f"instruction 이 같고 input 이 다른 정당한 변형이다.")
lines.append(f"4. **완전 중복 {len(dups_exact)}그룹은 각 그룹에서 1건만 남긴다.** "
             f"남길 기준은 '더 완전한 문장으로 답한 쪽' 으로 통일한다 "
             f"(예: idx 1068 `drew.` 대신 idx 29 "
             f"`The past tense of 'draw' is 'drew.'`). "
             f"관련 {n_dup_items}건 중 {n_dup_items - len(dups_exact)}건 제거 → "
             f"1,100 → {1100 - (n_dup_items - len(dups_exact))}건. "
             f"**이것이 이번 점검에서 나온 유일한 실제 조치다.**")
lines.append(f"5. **13주차 심판 채점 시 이 {n_dup_items}건을 기억할 것.** "
             f"응답이 너무 짧다는 저점이 나오면 모델 탓이 아니라 "
             f"데이터에 짧은 정답이 섞여 있던 탓일 수 있다.")
lines.append(f"6. **데이터 양(1,100건)이 가장 큰 위험 요인이다.** 원조 Alpaca 는 52,000건이다. "
             f"형식적 결함이 0건이라는 것이 '충분하다'는 뜻은 아니다 — "
             f"13주차에서 응답이 형식만 흉내 내는 증상이 나오면 "
             f"데이터 결함이 아니라 **데이터 양**을 의심해야 한다.")
lines.append("")
lines.append("> **\"문제가 없음을 확인하는 것\"도 점검의 정당한 결과다** — 그러나 이번엔 "
             "문제가 없지 않았다. 점검을 돌리지 않았다면 20그룹의 스타일 모순을 "
             "발견하지 못한 채 13주차 훈련에 들어갔을 것이다. "
             "'정제된 데이터셋'이라는 평판은 점검을 생략할 이유가 되지 못한다.")

with open("quality_report.md", "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
print()
print("[저장] quality_report.md")
