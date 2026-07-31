"""P3-5 — 위치 임베딩 유무에 따른 표현 차이 관찰."""
import tiktoken
import torch
import torch.nn as nn

enc = tiktoken.get_encoding("gpt2")

# 1) 같은 토큰이 두 번 나오는 짧은 시퀀스
#
# ⚠️ 교재 예시 "the cat and the dog" 은 이 실험에 쓸 수 없다.
#    GPT-2 BPE 는 공백을 토큰에 붙여 다루므로 문장 맨 앞의 'the'(ID 1169)와
#    중간의 ' the'(ID 262)가 서로 **다른 토큰**이 된다 → 중복 토큰이 0개.
#    반복되는 단어가 문장 맨 앞에 오지 않게 하면 두 번 모두 ' the'(262)가 된다.
text = "I saw the cat and the dog"
ids = enc.encode(text)
pieces = [enc.decode([i]) for i in ids]

print("=== 1) 시퀀스 준비 ===")
print(f"문장: {text!r}")
print(f"토큰 ID: {ids}")
print(f"조각    : {pieces}")

# 'the' 가 나타난 위치를 찾는다 (' the' 는 앞에 공백이 붙어 ID가 다르다)
positions = {}
for idx, tid in enumerate(ids):
    positions.setdefault(tid, []).append(idx)
dup = {tid: pos for tid, pos in positions.items() if len(pos) > 1}
print(f"두 번 이상 나온 토큰 ID: { {k: v for k, v in dup.items()} }")
if not dup:
    raise SystemExit("중복 토큰이 없다 — 문장을 바꿔야 한다")

dup_id = next(iter(dup))
p1, p2 = dup[dup_id][0], dup[dup_id][1]
print(f"→ 검사 대상: ID {dup_id} ({enc.decode([dup_id])!r}) 가 위치 {p1} 와 {p2} 에 등장")

OUTPUT_DIM = 16
torch.manual_seed(123)
tok_emb_layer = nn.Embedding(enc.n_vocab, OUTPUT_DIM)
pos_emb_layer = nn.Embedding(len(ids), OUTPUT_DIM)

tok_emb = tok_emb_layer(torch.tensor(ids))                       # [T, D]
pos_emb = pos_emb_layer(torch.arange(len(ids)))                  # [T, D]
with_pos = tok_emb + pos_emb

# 2) 위치 임베딩 없이
v1, v2 = tok_emb[p1], tok_emb[p2]
eq_no_pos = torch.equal(v1, v2)
norm_no_pos = torch.norm(v1 - v2).item()

# 3) 위치 임베딩을 더한 후
w1, w2 = with_pos[p1], with_pos[p2]
eq_with_pos = torch.equal(w1, w2)
norm_with_pos = torch.norm(w1 - w2).item()

print()
print("=== 2) 위치 임베딩 없이 ===")
print(f"위치 {p1} 벡터[:4]: {v1[:4].tolist()}")
print(f"위치 {p2} 벡터[:4]: {v2[:4].tolist()}")
print(f"torch.equal: {eq_no_pos}")
print(f"차이의 L2 노름: {norm_no_pos:.10f}")

print()
print("=== 3) 위치 임베딩을 더한 후 ===")
print(f"위치 {p1} 벡터[:4]: {w1[:4].tolist()}")
print(f"위치 {p2} 벡터[:4]: {w2[:4].tolist()}")
print(f"torch.equal: {eq_with_pos}")
print(f"차이의 L2 노름: {norm_with_pos:.6f}")

lines = [
    "# pos_experiment.md — 위치 임베딩 관찰 실험 (P3-5 산출물)",
    "",
    f"문장: `{text}`  → 토큰 {len(ids)}개",
    f"토큰 ID: `{ids}`",
    f"조각: `{pieces}`",
    "",
    f"검사 대상: ID **{dup_id}** (`{enc.decode([dup_id])}`) 가 위치 **{p1}** 와 **{p2}** 에 두 번 등장",
    "",
    "| 조건 | torch.equal | 차이의 L2 노름 | 해석 |",
    "|---|---|---|---|",
    f"| 위치 임베딩 **없이** | `{eq_no_pos}` | **{norm_no_pos:.10f}** | 완전 동일 — 모델 입장에서 두 'the' 는 구별 불가 |",
    f"| 위치 임베딩 **더한 후** | `{eq_with_pos}` | **{norm_with_pos:.6f}** | 서로 다름 — 위치 정보가 주입되었다 |",
    "",
    "## 검증 — 위치 임베딩이 없다면 구분 불가능해지는 문장 쌍",
    "",
    "```",
    "A: The dog bit the man.",
    "B: The man bit the dog.",
    "```",
    "",
    "두 문장은 **완전히 동일한 토큰 집합**(`The`, `dog`, `bit`, `the`, `man`, `.`)으로 구성되고",
    "개수도 같다. 위치 임베딩이 없으면 각 토큰의 벡터가 순서와 무관하게 고정되므로,",
    "모델이 보는 입력 집합은 두 문장에서 **원소만 같고 순서 정보가 전혀 없다**.",
    "누가 물었고 누가 물렸는지 — 즉 문장의 의미를 뒤집는 정보 — 를 복원할 방법이 사라진다.",
    "",
    "(어텐션 자체도 순서에 무관한 연산이다. 가중합은 덧셈이므로 순서를 바꿔도 같은 값이 나온다.",
    " 그래서 순서 정보는 **입력 단계에서 벡터에 심어 넣어야** 한다.)",
]
with open("pos_experiment.md", "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
print()
print("→ pos_experiment.md 저장")
