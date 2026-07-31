"""P5-6 — d_out 고정, num_heads 변화가 파라미터·속도에 미치는 영향 측정."""
import time

import torch

from multihead import MultiHeadAttention

D = 768
CONTEXT = 1024
HEADS = [1, 4, 12]
device = "cuda" if torch.cuda.is_available() else "cpu"

print(f"device = {device}")
if device == "cuda":
    print(f"GPU = {torch.cuda.get_device_name(0)}")

rows = []
for num_heads in HEADS:
    torch.manual_seed(123)
    mha = MultiHeadAttention(
        d_in=D, d_out=D, context_length=CONTEXT, dropout=0.0, num_heads=num_heads
    ).to(device)
    mha.eval()

    total = sum(p.numel() for p in mha.parameters())
    head_dim = mha.head_dim

    x = torch.rand(4, CONTEXT, D, device=device)

    # 측정 규약: 워밍업 3회 후 10회 평균, 측정 전후 synchronize
    with torch.no_grad():
        for _ in range(3):
            mha(x)
        if device == "cuda":
            torch.cuda.synchronize()

        t0 = time.perf_counter()
        for _ in range(10):
            mha(x)
        if device == "cuda":
            torch.cuda.synchronize()
        t1 = time.perf_counter()

    avg_ms = (t1 - t0) / 10 * 1000
    rows.append((num_heads, head_dim, total, avg_ms))

    del mha, x
    if device == "cuda":
        torch.cuda.empty_cache()

lines = []
lines.append("# heads_experiment.md — 헤드 수 실험: 통념 깨기 (P5-6 산출물)")
lines.append("")
lines.append(f"고정: d_in=d_out={D}, context_length={CONTEXT}, dropout=0.0, "
             f"입력 [4, {CONTEXT}, {D}]")
lines.append(f"측정: {device}"
             + (f" ({torch.cuda.get_device_name(0)})" if device == "cuda" else "")
             + " / 워밍업 3회 후 10회 평균, 측정 전후 torch.cuda.synchronize()")
lines.append("")
lines.append("| num_heads | head_dim | 파라미터 수 | 평균 forward 시간(ms) |")
lines.append("|---|---|---|---|")
for nh, hd, tot, ms in rows:
    lines.append(f"| {nh} | {hd} | {tot:,} | {ms:.2f} |")
lines.append("")

param_set = {r[2] for r in rows}
lines.append("## 파라미터 수 열에서 발견되는 사실")
lines.append("")
if len(param_set) == 1:
    lines.append(f"**세 경우의 파라미터 수가 완전히 동일하다: {rows[0][2]:,}개.**")
else:
    lines.append(f"**파라미터 수가 다르다: {sorted(param_set)} — 예상과 다름!**")
lines.append("")
lines.append("헤드를 나누는 것은 **같은 크기의 투영 출력을 조각내 병렬로 보는 것**이지,")
lines.append("투영을 늘리는 게 아니다. W_query/W_key/W_value/out_proj 는 항상")
lines.append(f"`Linear({D} → {D})` 이고, 헤드 수는 그 출력 {D}차원을 몇 조각으로")
lines.append("자를지만 정한다. 그래서 head_dim 만 변한다:")
lines.append("")
for nh, hd, tot, ms in rows:
    lines.append(f"- num_heads={nh:2d} → head_dim = {D} / {nh} = **{hd}**")
lines.append("")
times = [r[3] for r in rows]
lines.append(f"시간은 {min(times):.2f} ~ {max(times):.2f} ms 로 "
             f"{max(times)/min(times):.2f}배 이내 — 대체로 비슷한 수준이다")
lines.append("(구현·커널에 따라 소폭 차이. 총 FLOPs 가 같으므로 큰 차이가 날 이유가 없다).")

with open("heads_experiment.md", "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")

print()
print("\n".join(lines))
