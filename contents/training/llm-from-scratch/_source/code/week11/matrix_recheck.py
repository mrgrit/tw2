"""P11-6 재확인 — 355M / (b) 가 124M / (b) 보다 낮은 이유 규명.

매트릭스 실측:
  124M / (b) test 96.33%  (에폭 4 에서 train 정확도 100% 도달)
  355M / (b) test 85.00%  (에폭 5 까지 train 정확도 82.5~95% — 수렴 안 함)
교재는 "355M ≥ 124M" 을 예상한다. 가설: 355M/(b) 는 **미수렴**이다.
  · 355M 은 24층인데 (b) 는 마지막 1개 블록만 푼다 → 상대적으로 더 얕게 푼 셈
  · lr 5e-5 · 5 에폭이 355M 의 마지막 블록을 맞추기에 부족
에폭을 늘리면 따라잡는지 확인한다. 따라잡으면 '교재 예상은 맞되 5에폭이
부족한 것'이고, 못 따라잡으면 '전략 (b) 는 355M 에 부적합'이다.
"""
import time

import torch

import common  # noqa: F401
from common import device
from spam_data import build_loaders
from spam_finetune import (SEED, calc_accuracy_loader, load_and_modify,
                           train_classifier_simple)

train_loader, val_loader, test_loader, *_ = build_loaders(batch_size=8)

print("=" * 74)
print("355M / (b) 를 에폭만 5 → 20 으로 늘려 재훈련 (lr·시드 동일)")
print("=" * 74)

torch.cuda.empty_cache()
torch.cuda.reset_peak_memory_stats()
model, cfg = load_and_modify("gpt2-medium (355M)", strategy="b", verbose=False)
torch.manual_seed(SEED)
opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],
                        lr=5e-5, weight_decay=0.1)

torch.cuda.synchronize()
t0 = time.perf_counter()
_, _, tr_accs, va_accs, _ = train_classifier_simple(
    model, train_loader, val_loader, opt, device,
    num_epochs=20, eval_freq=10_000, eval_iter=5, use_bf16=True)
torch.cuda.synchronize()
elapsed = time.perf_counter() - t0

test20 = calc_accuracy_loader(test_loader, model, device)
train20 = calc_accuracy_loader(train_loader, model, device)
print()
print(f"20 에폭 후: train {train20*100:.2f}% / test **{test20*100:.2f}%** "
      f"({elapsed:.1f}초)")
print()
print("에폭별 train/val 정확도(표본 5배치):")
for i, (a, b) in enumerate(zip(tr_accs, va_accs), 1):
    mark = "  ← 5에폭 지점(매트릭스 측정점)" if i == 5 else ""
    print(f"  {i:>2}: train {a*100:6.2f}% | val {b*100:6.2f}%{mark}")

del model, opt
torch.cuda.empty_cache()

print()
print("=" * 74)
print("결론")
print("=" * 74)
print(f"  124M / (b) 5에폭  : test 96.33%")
print(f"  355M / (b) 5에폭  : test 85.00%")
print(f"  355M / (b) 20에폭 : test {test20*100:.2f}%")
if test20 > 0.9633:
    print("  → 355M/(b) 는 **미수렴**이었다. 에폭을 늘리면 124M 을 넘어선다.")
    print("    교재의 '355M ≥ 124M' 은 옳으나, 5 에폭 고정이라는 공통 조건이")
    print("    355M 에는 부족하다. 교재가 조건을 명시하지 않은 것이 문제다.")
else:
    print("  → 에폭을 4배로 늘려도 124M/(b) 를 넘지 못한다.")
    print("    '355M ≥ 124M' 은 전략 (b) 에서는 성립하지 않는다.")
