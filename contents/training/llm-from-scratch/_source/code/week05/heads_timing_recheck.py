"""P5-6 시간 측정 재검증 — 순서 편향·측정 노이즈를 배제한다.

교재는 "시간은 대체로 비슷한 수준"이라고 예상한다. 1차 측정에서 3배 차이가 나왔으므로
① 측정 순서를 뒤집고 ② 3회 반복해 재현성을 본다.
"""
import time

import torch

from multihead import MultiHeadAttention

D, CONTEXT = 768, 1024
device = "cuda"


def measure(num_heads):
    torch.manual_seed(123)
    mha = MultiHeadAttention(D, D, CONTEXT, 0.0, num_heads).to(device).eval()
    x = torch.rand(4, CONTEXT, D, device=device)
    with torch.no_grad():
        for _ in range(5):
            mha(x)
        torch.cuda.synchronize()
        t0 = time.perf_counter()
        for _ in range(20):
            mha(x)
        torch.cuda.synchronize()
        t1 = time.perf_counter()
    ms = (t1 - t0) / 20 * 1000
    del mha, x
    torch.cuda.empty_cache()
    return ms


print("=== 정순 [1, 4, 12] x 3회 ===")
fwd = {h: [] for h in (1, 4, 12)}
for trial in range(3):
    for h in (1, 4, 12):
        fwd[h].append(measure(h))
    print(f"  trial {trial + 1}: " + "  ".join(f"h={h} {fwd[h][-1]:.2f}ms" for h in (1, 4, 12)))

print()
print("=== 역순 [12, 4, 1] x 3회 ===")
rev = {h: [] for h in (1, 4, 12)}
for trial in range(3):
    for h in (12, 4, 1):
        rev[h].append(measure(h))
    print(f"  trial {trial + 1}: " + "  ".join(f"h={h} {rev[h][-1]:.2f}ms" for h in (12, 4, 1)))

print()
print("| num_heads | head_dim | 정순 평균(ms) | 역순 평균(ms) | 전체 평균(ms) |")
print("|---|---|---|---|---|")
avgs = {}
for h in (1, 4, 12):
    a = sum(fwd[h]) / len(fwd[h])
    b = sum(rev[h]) / len(rev[h])
    c = (sum(fwd[h]) + sum(rev[h])) / (len(fwd[h]) + len(rev[h]))
    avgs[h] = c
    print(f"| {h} | {D // h} | {a:.2f} | {b:.2f} | **{c:.2f}** |")

ratio = max(avgs.values()) / min(avgs.values())
print()
print(f"최대/최소 배율 = {ratio:.2f}배")
print("판정:", "교재 서술('소폭 차이')과 부합" if ratio < 1.5
      else f"교재 서술과 불일치 — {ratio:.2f}배는 '소폭'이 아니다")
print()
print("원인 분석: 이 구현은 flash-attention 이 아니라 명시적 [b,heads,T,T] 점수 행렬을")
print("만든다. num_heads 가 커지면 head_dim 이 작아져(768→64) 헤드별 matmul 이")
print("작고 많아지므로 GPU 코어 활용률이 떨어진다. 총 FLOPs 는 같지만 커널 효율이 다르다.")
print("softmax 대상 원소 수도 b*heads*T*T 로 heads 에 비례해 늘어난다:")
for h in (1, 4, 12):
    print(f"  heads={h:2d}: softmax 원소 4*{h}*1024*1024 = {4 * h * 1024 * 1024:,}")
