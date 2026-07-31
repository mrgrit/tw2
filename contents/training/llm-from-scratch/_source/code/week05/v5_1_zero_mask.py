"""V5-1 — 경계 사례: -inf 대신 0 으로 masked_fill 하면 왜 잘못되는가."""
import math

import torch

from causal_attention import SelfAttention_v2
from inputs import inputs

torch.set_printoptions(precision=4, sci_mode=False)

torch.manual_seed(789)
sa = SelfAttention_v2(3, 2)
q, k = sa.W_query(inputs), sa.W_key(inputs)
d_k = k.shape[-1]
scores = q @ k.T
T = scores.shape[0]
mask_up = torch.triu(torch.ones(T, T), diagonal=1).bool()

w_inf = torch.softmax(scores.masked_fill(mask_up, -torch.inf) / d_k ** 0.5, dim=-1)
w_zero = torch.softmax(scores.masked_fill(mask_up, 0.0) / d_k ** 0.5, dim=-1)

print("=== -inf 마스킹 (정답) ===")
print(torch.round(w_inf, decimals=4))
print()
print("=== 0 마스킹 (오답) ===")
print(torch.round(w_zero, decimals=4))
print()

leak_inf = (w_inf * mask_up).sum(dim=-1)
leak_zero = (w_zero * mask_up).sum(dim=-1)
print("미래 위치에 남은 가중치 합 (행별):")
print("| 행 | -inf 방식 | 0 방식 |")
print("|---|---|---|")
for i in range(T):
    print(f"| {i} | {float(leak_inf[i]):.6f} | **{float(leak_zero[i]):.6f}** |")

print()
print(f"0 방식 첫 행: {torch.round(w_zero[0], decimals=4).tolist()}")
print(f"  → 자기 자신만 봐야 하는데 미래 5개에 총 {float(leak_zero[0]):.4f} 만큼 표를 줬다")
print(f"  → 즉 첫 토큰이 자기 자신에 준 가중치는 {float(w_zero[0][0]):.4f} 로, 1.0 이 아니다")

print()
print("설명 (두 문장):")
print("  softmax 는 exp 를 적용한다. e^0 = 1 이므로 0 으로 마스킹한 자리는 "
      "'가중치 1의 후보'로 살아남아")
print("  정규화 분모에 들어가고, 미래 토큰이 여전히 0 이 아닌 가중치를 받는다. "
      "반면 e^(-inf) = 0 이므로")
print("  -inf 자리는 분자와 분모에서 정확히 사라진다.")
print()
print(f"  참고: e^0 = {math.exp(0)}, e^(-inf) = {math.exp(-math.inf)}")

print()
print("판정:", "PASS — 0 마스킹이 미래에 0이 아닌 가중치를 남기는 것을 수치로 확인"
      if float(leak_zero[0]) > 0.1 else "FAIL")
