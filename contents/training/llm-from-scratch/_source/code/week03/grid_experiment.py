"""P3-2 — (max_length, stride) 조합이 데이터셋에 미치는 영향 측정.

len(dataset) 기준으로 센다(배치·drop_last 영향 배제).
교재 공식 ⌈(N − max_length) ÷ stride⌉ 로도 계산해 병기한다.
"""
import math

import tiktoken

from dataset import GPTDatasetV1

with open("the-verdict.txt", "r", encoding="utf-8") as f:
    raw_text = f.read()

tokenizer = tiktoken.get_encoding("gpt2")
N = len(tokenizer.encode(raw_text))

COMBOS = [(4, 1), (4, 4), (256, 128), (256, 256)]

rows = []
for max_length, stride in COMBOS:
    ds = GPTDatasetV1(raw_text, tokenizer, max_length, stride)
    measured = len(ds)

    # 교재 공식
    formula = math.ceil((N - max_length) / stride)

    # 실제 range 기반 계산 (구현이 쓰는 식)
    actual_range = len(range(0, N - max_length, stride))

    overlap = max(0, max_length - stride)  # 인접 샘플 간 중복 토큰 수
    rows.append((max_length, stride, measured, formula, actual_range, overlap))

lines = []
lines.append("# grid_experiment.md — stride·context 그리드 실험 (P3-2 산출물)")
lines.append("")
lines.append(f"전체 BPE 토큰 수 N = **{N}**")
lines.append("")
lines.append("| max_length | stride | 샘플 수(측정) | 공식 ⌈(N−max_length)÷stride⌉ | 공식 일치 | 인접 샘플 간 중복 토큰 수 | 관찰 |")
lines.append("|---|---|---|---|---|---|---|")
for ml, st, m, f, ar, ov in rows:
    match = "O" if m == f else f"**X (차이 {m - f})**"
    if st < ml:
        obs = f"창이 {ov}/{ml} 만큼 겹친다 — 같은 내용을 사실상 {ml // st}번 학습"
    else:
        obs = "중복 0 — 각 토큰이 정확히 한 번만 쓰인다"
    lines.append(f"| {ml} | {st} | {m} | {f} | {match} | {ov} | {obs} |")

lines.append("")
lines.append("## 공식과 측정값의 관계")
lines.append("")
lines.append("구현은 `range(0, N - max_length, stride)` 를 순회한다. 이 range 의 길이는")
lines.append("정확히 `⌈(N − max_length) ÷ stride⌉` 이므로 공식과 측정값이 일치한다.")
lines.append("")
for ml, st, m, f, ar, ov in rows:
    lines.append(f"- `(ml={ml}, st={st})`: len(range(0, {N}−{ml}, {st})) = {ar}, "
                 f"공식 = ⌈{N - ml}/{st}⌉ = {f}, 측정 = {m}")

with open("grid_experiment.md", "w", encoding="utf-8") as fp:
    fp.write("\n".join(lines) + "\n")

print("\n".join(lines))
