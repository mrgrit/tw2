"""P4-1 + P4-2 — 단순 어텐션: 쿼리 하나 추적 → 전체 행렬화.

학습 가중치(W_q/W_k/W_v)를 쓰지 않는다. 임베딩을 그대로 비교한다.
"""
import torch

from inputs import inputs, tokens

torch.set_printoptions(precision=4, sci_mode=False)

# ==========================================================================
# P4-1 — 두 번째 토큰(journey, 인덱스 1)을 쿼리로 3단계 추적
# ==========================================================================
print("=" * 66)
print("P4-1 — 쿼리 = inputs[1] (journey)")
print("=" * 66)

query = inputs[1]

# 1단계: 6개 토큰 각각과의 내적으로 점수 계산
attn_scores_2 = torch.empty(inputs.shape[0])
for i, x_i in enumerate(inputs):
    attn_scores_2[i] = torch.dot(x_i, query)

print("\n1) 점수 (내적):")
print("  ", torch.round(attn_scores_2, decimals=4).tolist())
for t, s in zip(tokens, attn_scores_2.tolist()):
    print(f"     {t:9} {s:.4f}")

# 2단계: softmax 로 정규화
attn_weights_2 = torch.softmax(attn_scores_2, dim=0)
print("\n2) 가중치 (softmax):")
print("  ", torch.round(attn_weights_2, decimals=4).tolist())
print(f"   합계: {attn_weights_2.sum().item():.4f}")

# 3단계: 가중합으로 문맥 벡터
context_vec_2 = torch.zeros(query.shape)
for i, x_i in enumerate(inputs):
    context_vec_2 += attn_weights_2[i] * x_i

print("\n3) 문맥 벡터 z2:")
print("  ", torch.round(context_vec_2, decimals=4).tolist())

# 손계산 검산 — 첫 점수
manual = 0.43 * 0.55 + 0.15 * 0.87 + 0.89 * 0.66
print(f"\n손계산 검산: 0.43*0.55 + 0.15*0.87 + 0.89*0.66 = {manual:.4f}")
print(f"  코드 값 attn_scores_2[0] = {attn_scores_2[0].item():.4f}  → 일치 "
      f"{abs(manual - attn_scores_2[0].item()) < 1e-6}")

# ==========================================================================
# P4-2 — 전체 행렬화
# ==========================================================================
print()
print("=" * 66)
print("P4-2 — 모든 토큰에 대한 어텐션 (루프 vs 행렬)")
print("=" * 66)

# 1) 루프 버전
contexts_loop = torch.empty(inputs.shape[0], inputs.shape[1])
weights_loop = torch.empty(inputs.shape[0], inputs.shape[0])
for q_idx, q in enumerate(inputs):
    scores = torch.empty(inputs.shape[0])
    for i, x_i in enumerate(inputs):
        scores[i] = torch.dot(x_i, q)
    w = torch.softmax(scores, dim=0)
    weights_loop[q_idx] = w
    ctx = torch.zeros(q.shape)
    for i, x_i in enumerate(inputs):
        ctx += w[i] * x_i
    contexts_loop[q_idx] = ctx

# 2) 행렬 버전
attn_scores = inputs @ inputs.T
attn_weights = torch.softmax(attn_scores, dim=-1)
contexts_matrix = attn_weights @ inputs

print("\n행렬 버전 가중치 (6x6):")
print(torch.round(attn_weights, decimals=4))
print("\n행렬 버전 문맥 (6x3):")
print(torch.round(contexts_matrix, decimals=4))

# 3) 두 버전 일치 확인
same = torch.allclose(contexts_loop, contexts_matrix, atol=1e-6)
print(f"\n3) 루프 == 행렬 (allclose): {same}")

# 4) 각 행 합이 1인지
row_sums = attn_weights.sum(dim=-1)
print(f"4) 각 행 합: {torch.round(row_sums, decimals=6).tolist()}")
print(f"   전부 1인가: {torch.allclose(row_sums, torch.ones(6), atol=1e-6)}")

# 2번째 행 == z2
row2_match = torch.allclose(contexts_matrix[1], context_vec_2, atol=1e-6)
print(f"\n행렬 버전 2번째 행 == P4-1 의 z2: {row2_match}")
print(f"   행렬[1] = {torch.round(contexts_matrix[1], decimals=4).tolist()}")
print(f"   z2      = {torch.round(context_vec_2, decimals=4).tolist()}")

if __name__ == "__main__":
    pass
