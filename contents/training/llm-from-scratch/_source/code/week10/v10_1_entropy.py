"""V10-1 — "T→0 극한 = greedy" 를 표본으로 검증하고 T별 엔트로피 단조성을 확인."""
import math

import torch

from decoding import INVERSE_VOCAB, NEXT_TOKEN_LOGITS, VOCAB, softmax_with_temperature

N = 1000
argmax_id = int(torch.argmax(NEXT_TOKEN_LOGITS))
print(f"argmax 단어 = {INVERSE_VOCAB[argmax_id]} (인덱스 {argmax_id})")
print()

print("=" * 66)
print("① T=0.01 로 1000회 추첨 — 전 회차가 argmax 단어와 일치하는가")
print("=" * 66)
torch.manual_seed(123)
probs001 = softmax_with_temperature(NEXT_TOKEN_LOGITS, 0.01)
sample = torch.multinomial(probs001, num_samples=N, replacement=True)
cnt = torch.bincount(sample, minlength=len(VOCAB))
same = int(cnt[argmax_id])
print(f"  forward 선택 횟수 : {same} / {N}")
nonzero = [(INVERSE_VOCAB[i], int(cnt[i])) for i in range(len(VOCAB)) if cnt[i] > 0]
print(f"  1회 이상 뽑힌 단어: {nonzero}")
print(f"  T=0.01 에서 forward 확률 = {probs001[argmax_id].item():.12f}")
print(f"  → 판정: {'PASS' if same == N else 'FAIL'}  ({same}/{N})")

print()
print("=" * 66)
print("② T별 분포 엔트로피 — T 가 커질수록 단조 증가하는가")
print("=" * 66)


def entropy(p):
    """섀넌 엔트로피 (nats). p log p 는 p=0 에서 0 으로 취급."""
    p = p[p > 0]
    return float(-(p * p.log()).sum())


TEMPS = [0.01, 0.1, 1.0, 5.0]
max_ent = math.log(len(VOCAB))
print(f"| T | 엔트로피(nats) | 최대치 대비 | 유효 후보 수 exp(H) | 최빈 확률 |")
print(f"|---|---|---|---|---|")
ents = []
for T in TEMPS:
    p = softmax_with_temperature(NEXT_TOKEN_LOGITS, T)
    h = entropy(p)
    ents.append(h)
    print(f"| {T} | {h:.6f} | {h/max_ent*100:5.2f}% | {math.exp(h):.3f} | "
          f"{p.max().item():.6f} |")
print(f"\n(어휘 9개의 최대 엔트로피 = ln 9 = {max_ent:.6f})")

mono = all(ents[i] < ents[i + 1] for i in range(len(ents) - 1))
print(f"\n단조 증가 여부: {' < '.join(f'{e:.4f}' for e in ents)}  → {mono}")
print(f"→ 판정: {'PASS' if mono else 'FAIL'}")

print()
print("=" * 66)
print("V10-1 통과 기준 종합")
print("=" * 66)
print(f"  T=0.01 에서 {same}/1000 forward            : {'PASS' if same == N else 'FAIL'}")
print(f"  엔트로피 단조 증가                        : {'PASS' if mono else 'FAIL'}")
