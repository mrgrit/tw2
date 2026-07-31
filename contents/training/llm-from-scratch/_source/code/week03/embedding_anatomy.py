"""P3-3 — nn.Embedding 의 동작 원리 해부 (장난감 예제).

핵심 증명: 임베딩 조회 == 원-핫 벡터 × 가중치 행렬
"""
import torch
import torch.nn as nn

torch.manual_seed(123)
vocab_size, output_dim = 6, 3
embedding = nn.Embedding(vocab_size, output_dim)

print("=== 1) 가중치 행렬 전체 (vocab_size=6, output_dim=3) ===")
print(embedding.weight)

print()
print("=== 2) 토큰 ID [3] 조회 vs 가중치 행렬의 3번 행 ===")
looked_up = embedding(torch.tensor([3]))
row3 = embedding.weight[3]
print("임베딩 조회 embedding(tensor([3])):", looked_up)
print("가중치 행렬 3번 행 weight[3]      :", row3)
print("같은가? torch.equal:", torch.equal(looked_up[0], row3))

print()
print("=== 3) 토큰 ID [2, 3, 5, 1] 조회 ===")
ids = torch.tensor([2, 3, 5, 1])
out = embedding(ids)
print(out)
print("shape:", tuple(out.shape))

print()
print("=== 4) 동치성 증명: 원-핫 행렬(4x6) @ 가중치(6x3) ===")
onehot = torch.nn.functional.one_hot(ids, num_classes=vocab_size).float()
print("원-핫 행렬 (4x6):")
print(onehot)
matmul = onehot @ embedding.weight
print("\n원-핫 @ 가중치 결과:")
print(matmul)
print("\n임베딩 조회 결과:")
print(out)
allclose = torch.allclose(matmul, out)
print("\ntorch.allclose(원-핫 행렬곱, 임베딩 조회) =", allclose)

print()
print("=== 연산량 관점: 왜 행렬곱 대신 조회로 구현하는가 ===")
# GPT-2 규모로 비교
V, D, T = 50257, 768, 1024
matmul_flops = T * V * D * 2          # (T x V) @ (V x D) 의 곱셈-덧셈
lookup_ops = T * D                    # 행 T개를 그대로 복사
print(f"GPT-2 규모(어휘 {V:,}, 차원 {D}, 토큰 {T:,}) 기준")
print(f"  원-핫 행렬곱: 약 {matmul_flops:,} FLOPs")
print(f"  행 조회     : 약 {lookup_ops:,} 번의 복사")
print(f"  → 배율 {matmul_flops / lookup_ops:,.0f}배")
print("원-핫 벡터는 한 자리만 1이고 나머지 50,256자리가 0이다. 그 0들과의 곱셈은 전부 낭비다.")
print("결과가 '가중치 행렬의 한 행'임을 알고 있으므로, 곱하지 않고 그 행을 바로 꺼내면 된다.")
print("메모리도 마찬가지 — 원-핫 행렬 자체를 만들면 T x V 크기의 텐서가 필요하다.")
