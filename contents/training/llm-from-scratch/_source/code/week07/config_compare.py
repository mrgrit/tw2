"""P7-5 — GPT-2 4개 크기의 구성·파라미터·메모리 비교 (연습문제 4.2).

측정 후 즉시 del + 가비지 컬렉션으로 메모리를 해제한다(교재 7.11 트러블슈팅).
"""
import gc

import torch

from gpt_model import GPTModel

BASE = {
    "vocab_size": 50257,
    "context_length": 1024,
    "drop_rate": 0.1,
    "qkv_bias": False,
}

SIZES = [
    ("small",  768, 12, 12, "124M"),
    ("medium", 1024, 24, 16, "355M"),
    ("large",  1280, 36, 20, "774M"),
    ("xl",     1600, 48, 25, "1.5B"),
]

rows = []
for name, emb, layers, heads, nickname in SIZES:
    cfg = dict(BASE, emb_dim=emb, n_layers=layers, n_heads=heads)
    torch.manual_seed(123)
    model = GPTModel(cfg)

    total = sum(p.numel() for p in model.parameters())
    head = sum(p.numel() for p in model.out_head.parameters())
    tied = total - head
    mem_gb = total * 4 / 1024 ** 3

    rows.append((name, emb, layers, heads, total, tied, mem_gb, nickname))
    print(f"{name:7} emb={emb:5} layers={layers:3} heads={heads:3}  "
          f"전체 {total:>13,}  tying {tied:>13,}  fp32 {mem_gb:.4f} GB")

    del model
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

lines = []
lines.append("# config_compare.md — GPT-2 4개 크기 비교 (P7-5 산출물, 연습문제 4.2)")
lines.append("")
lines.append("| 모델 | emb | layers | heads | 전체 파라미터 | 출력 헤드 제외(tying 기준) | float32 메모리(GB) | 통칭 | 부합 |")
lines.append("|---|---|---|---|---|---|---|---|---|")
for name, emb, layers, heads, total, tied, mem_gb, nickname in rows:
    # 통칭과의 부합 판정
    target = {"124M": 124e6, "355M": 355e6, "774M": 774e6, "1.5B": 1.5e9}[nickname]
    ok = abs(tied - target) / target < 0.05      # 5% 이내면 부합
    lines.append(f"| {name} | {emb} | {layers} | {heads} | {total:,} | **{tied:,}** | "
                 f"{mem_gb:.4f} | {nickname} | {'O' if ok else f'X ({tied/target:.3f}배)'} |")
lines.append("")
lines.append("## 통칭 부합 판정 (검증 항목)")
lines.append("")
for name, emb, layers, heads, total, tied, mem_gb, nickname in rows:
    target = {"124M": 124e6, "355M": 355e6, "774M": 774e6, "1.5B": 1.5e9}[nickname]
    lines.append(f"- **{name}** (통칭 {nickname}): tying 기준 {tied:,} = "
                 f"{tied/1e6:.1f}M → 통칭 대비 {tied/target:.4f}배 "
                 f"{'✅ 부합' if abs(tied-target)/target < 0.05 else '❌ 불일치'}")
lines.append("")
lines.append("## 관찰")
lines.append("")
lines.append(f"- small 열은 미션 1~2 정답지와 일치한다: 전체 {rows[0][4]:,} / "
             f"tying {rows[0][5]:,}")
lines.append(f"- float32 기준 xl 도 **{rows[-1][6]:.2f} GB** — Spark 통합 메모리 128GB 에")
lines.append(f"  **적재만이라면** 넉넉히 들어간다 (약 {128/rows[-1][6]:.0f}개 분량).")
lines.append("  단 '모델 적재'와 '훈련'의 메모리는 전혀 다른 이야기다 — 기울기·옵티마이저")
lines.append("  상태·활성값이 추가로 필요하다. 그 이유는 9주차에서 몸으로 알게 된다.")

with open("config_compare.md", "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")

print()
print("\n".join(lines))
