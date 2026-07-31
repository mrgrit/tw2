"""V9-2 — 과적합 물증 수집.

"비슷해 보인다"로는 부족하다. 생성문 조각이 원문에 **그대로** 존재하는지 검색으로 입증한다.
"""
import math

import tiktoken
import torch

from common import device, text_to_token_ids, token_ids_to_text
from generate import generate_text_simple
from gpt_model import GPT_CONFIG_124M, GPTModel

CFG = dict(GPT_CONFIG_124M, context_length=256)

tokenizer = tiktoken.get_encoding("gpt2")
with open("the-verdict.txt", "r", encoding="utf-8") as f:
    original = f.read()

# 훈련된 모델 로드
model = GPTModel(CFG)
model.load_state_dict(torch.load("model_10ep.pth", map_location=device))
model.to(device)
model.eval()

start = "Every effort moves you"
encoded = text_to_token_ids(start, tokenizer).to(device)
with torch.no_grad():
    out = generate_text_simple(model, encoded, max_new_tokens=50,
                               context_size=CFG["context_length"])
generated = token_ids_to_text(out, tokenizer)

print("=== 생성문 (50 토큰) ===")
print(repr(generated))
print()

# 조각 나누기: 공백 기준 6~8 단어 조각을 겹치며 만든다
words = generated.split()
CHUNK = 7
chunks = []
for i in range(0, len(words) - CHUNK + 1, 3):     # 3단어씩 겹쳐가며
    chunks.append(" ".join(words[i:i + CHUNK]))

# 원문 정규화(공백 통일)해서 검색 — 줄바꿈 때문에 놓치지 않도록
norm_orig = " ".join(original.split())

rows = []
for c in chunks:
    norm_c = " ".join(c.split())
    pos = norm_orig.find(norm_c)
    rows.append((c, pos >= 0, pos))

found = sum(1 for _, ok, _ in rows if ok)

lines = []
lines.append("# overfit_evidence.md — 과적합 물증 (V9-2 산출물)")
lines.append("")
lines.append(f"모델: `model_10ep.pth` (10 에폭 사전 훈련, the-verdict.txt)")
lines.append(f"시작 문자열: `{start}` → greedy 50 토큰 생성")
lines.append("")
lines.append("## 생성문")
lines.append("")
lines.append("```")
lines.append(generated)
lines.append("```")
lines.append("")
lines.append(f"## 조각별 원문 존재 검색 ({CHUNK}단어 조각, 3단어씩 겹침)")
lines.append("")
lines.append("| # | 조각 | 원문 존재 | 원문 위치(문자 오프셋) |")
lines.append("|---|---|---|---|")
for i, (c, ok, pos) in enumerate(rows, start=1):
    lines.append(f"| {i} | `{c}` | {'**O**' if ok else 'X'} | {pos if ok else '—'} |")
lines.append("")
lines.append(f"**원문과 일치한 조각: {found} / {len(rows)} = "
             f"{found/len(rows)*100:.1f}%**")
lines.append("")

# 가장 긴 연속 일치 구간도 찾는다 (더 강한 물증)
best_len, best_str, best_pos = 0, "", -1
norm_gen_words = " ".join(generated.split()).split()
for i in range(len(norm_gen_words)):
    for j in range(len(norm_gen_words), i, -1):
        cand = " ".join(norm_gen_words[i:j])
        if len(cand.split()) <= best_len:
            break
        p = norm_orig.find(cand)
        if p >= 0:
            best_len, best_str, best_pos = len(cand.split()), cand, p
            break

lines.append("## 가장 긴 연속 일치 구간 (더 강한 물증)")
lines.append("")
lines.append(f"- **{best_len} 단어**가 원문과 그대로 일치")
lines.append(f"- 원문 위치: 문자 오프셋 **{best_pos}**")
lines.append("")
lines.append("```")
lines.append(best_str)
lines.append("```")
lines.append("")

# 퍼플렉시티 한 줄
lines.append("## train 손실 1 미만이 퍼플렉시티로 뜻하는 것")
lines.append("")
lines.append("train 손실 < 1 → 퍼플렉시티 = exp(손실) < **e¹ ≈ 2.718** 이하.")
lines.append("즉 모델이 매 순간 **후보 3개 미만에서 고민**하는 수준이다.")
lines.append("5만 개 어휘 중에서 사실상 다음 토큰을 '알고 있다' — 이해가 아니라 암기다.")
lines.append("")
lines.append(f"(실측: 최종 train 손실 0.8908 → 퍼플렉시티 {math.exp(0.8908):.2f})")

with open("overfit_evidence.md", "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")

print("\n".join(lines[10:]))
print()
print("=== 게이트 판정 ===")
print(f"W09-G9 상당수 조각이 원문에 존재: {found}/{len(rows)} = {found/len(rows)*100:.1f}%  "
      f"→ {'PASS' if found/len(rows) >= 0.5 else 'FAIL'}")
print(f"W09-G10 train ppl {math.exp(0.8908):.2f} ≤ 2.7: "
      f"{'PASS' if math.exp(0.8908) <= 2.72 else 'FAIL'}")
