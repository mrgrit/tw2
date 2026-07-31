"""검사자(checker) 스크립트 — V6-1 통과 기준을 hermes 산출물에 그대로 적용.

교재 V6-1: "내 LayerNorm과 torch.nn.LayerNorm(emb_dim, eps=1e-5)를 동일 입력으로 비교.
공식 구현의 초기 가중치(weight=1, bias=0)와 내 초기값이 같으므로 출력이 torch.allclose 여야 한다."
통과 기준: allclose True.
"""
import torch
from layers import LayerNorm

torch.manual_seed(123)
x = torch.randn(2, 5)

mine = LayerNorm(5)
ref = torch.nn.LayerNorm(5, eps=1e-5)

out_mine = mine.forward(x)
out_ref = ref(x)

print("입력 shape:", tuple(x.shape))
print("내 출력[0]:", out_mine[0].tolist())
print("공식 출력[0]:", out_ref[0].tolist())
print()
print("W06-G2 allclose:", torch.allclose(out_mine, out_ref, atol=1e-5))
print()

# W06-G1: 마지막 차원 기준 평균 0 / 분산(unbiased=False) 1
m = out_mine.mean(dim=-1)
v = out_mine.var(dim=-1, unbiased=False)
print("마지막 차원 평균:", m.tolist())
print("마지막 차원 분산(unbiased=False):", v.tolist())
print("W06-G1 mean≈0:", torch.allclose(m, torch.zeros_like(m), atol=1e-4))
print("W06-G1 var≈1 :", torch.allclose(v, torch.ones_like(v), atol=1e-4))
print()

# 교재가 요구한 "학습 파라미터" 여부
print("nn.Module 인가:", isinstance(mine, torch.nn.Module))
print("scale 이 nn.Parameter 인가:", isinstance(mine.scale, torch.nn.Parameter))
print("shift 가 nn.Parameter 인가:", isinstance(mine.shift, torch.nn.Parameter))
