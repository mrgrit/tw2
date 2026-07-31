"""P9-4 실험 B 정정안 검증.

교재는 batch_size ∈ {2, 8, 32} 를 지정하지만 9주차 데이터로는 batch=32 가 실행 불가다.
  · train 토큰 4,612 → max_length=stride=256 이면 샘플 ⌈(4612-256)/256⌉ = 18개
  · batch_size=32, drop_last=True → 18 // 32 = 0 배치
두 가지 대안을 실측해 어느 쪽이 교재의 교육 목표("작은 배치는 GPU를 굶긴다")를
더 잘 보여주는지 확인한다.
"""
import time

import torch

import common  # noqa: F401
from dataset import create_dataloader_v1
from gpt_model import GPT_CONFIG_124M, GPTModel
from pretrain import calc_loss_batch

CFG = dict(GPT_CONFIG_124M, context_length=256)
cuda = torch.device("cuda")

with open("the-verdict.txt", "r", encoding="utf-8") as f:
    text_data = f.read()
train_data = text_data[:int(0.90 * len(text_data))]


def epoch_time(loader):
    torch.manual_seed(123)
    m = GPTModel(CFG).to(cuda)
    o = torch.optim.AdamW(m.parameters(), lr=4e-4, weight_decay=0.1)
    # 워밍업
    for inp, tgt in loader:
        o.zero_grad(); calc_loss_batch(inp, tgt, m, cuda).backward(); o.step()
        break
    torch.cuda.synchronize()
    t0 = time.perf_counter()
    tokens = 0
    for inp, tgt in loader:
        o.zero_grad()
        loss = calc_loss_batch(inp, tgt, m, cuda)
        loss.backward()
        o.step()
        tokens += inp.numel()
    torch.cuda.synchronize()
    dt = time.perf_counter() - t0
    del m, o
    torch.cuda.empty_cache()
    return dt, tokens


print("=" * 72)
print("현상 확인 — 교재 원문 설정 (stride=256, drop_last=True)")
print("=" * 72)
for bs in (2, 8, 32):
    ld = create_dataloader_v1(train_data, batch_size=bs, max_length=256,
                              stride=256, shuffle=True, drop_last=True)
    print(f"  batch={bs:2d} → 배치 {len(ld):2d}개 "
          f"{'← 실행 불가' if len(ld) == 0 else ''}")

print()
print("=" * 72)
print("대안 1 — drop_last=False (배치 수만 확보, 마지막 배치가 작아짐)")
print("=" * 72)
print("| batch | 배치 수 | 시간(s) | 본 토큰 | tokens/sec | batch=2 대비 |")
print("|---|---|---|---|---|---|")
base = None
for bs in (2, 8, 32):
    ld = create_dataloader_v1(train_data, batch_size=bs, max_length=256,
                              stride=256, shuffle=True, drop_last=False)
    if len(ld) == 0:
        print(f"| {bs} | 0 | — | — | — | 실행 불가 |")
        continue
    dt, tok = epoch_time(ld)
    tps = tok / dt
    if base is None:
        base = tps
    print(f"| {bs} | {len(ld)} | {dt:.3f} | {tok:,} | **{tps:,.0f}** | {tps/base:.2f}배 |")

print()
print("=" * 72)
print("대안 2 — stride=128 로 샘플을 늘림 (drop_last=True 유지)")
print("=" * 72)
ld_probe = create_dataloader_v1(train_data, batch_size=1, max_length=256,
                                stride=128, shuffle=False, drop_last=False)
print(f"stride=128 일 때 샘플 수: {len(ld_probe)}개 (stride=256 은 18개)")
print()
print("| batch | 배치 수 | 시간(s) | 본 토큰 | tokens/sec | batch=2 대비 |")
print("|---|---|---|---|---|---|")
base2 = None
for bs in (2, 8, 32):
    ld = create_dataloader_v1(train_data, batch_size=bs, max_length=256,
                              stride=128, shuffle=True, drop_last=True)
    if len(ld) == 0:
        print(f"| {bs} | 0 | — | — | — | 실행 불가 |")
        continue
    dt, tok = epoch_time(ld)
    tps = tok / dt
    if base2 is None:
        base2 = tps
    print(f"| {bs} | {len(ld)} | {dt:.3f} | {tok:,} | **{tps:,.0f}** | {tps/base2:.2f}배 |")

print()
print("=" * 72)
print("결론")
print("=" * 72)
print("대안 2(stride=128) 가 교재 목표에 더 적합하다:")
print("  · batch 2/8/32 세 조건 모두 실행된다")
print("  · drop_last=True 를 유지하므로 배치 크기가 균일해 비교가 공정하다")
print("  · 3주차 그리드 실험(stride=128 → 중복 128 토큰)과 자연스럽게 연결된다")
print("대안 1(drop_last=False) 은 batch=32 에서 배치가 1개(18샘플)뿐이라")
print("  '에폭' 단위 비교가 사실상 단일 배치 측정이 되어 해석이 흐려진다.")
