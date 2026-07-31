"""P11-6 — 동결 전략 3종 × 모델 크기 2종 = 6조합 비교 실험.

[축 1 — 동결 전략] a. 새 헤드만 / b. 헤드+마지막 블록+최종LN(교재) / c. 전층
[축 2 — 모델]     GPT-2 124M, 355M
[공통] 시드 123, 5 에폭, lr 5e-5, bf16 autocast, 조합마다 모델 완전 해제
"""
import time

import torch

import common  # noqa: F401
from common import device
from spam_data import build_loaders
from spam_finetune import (SEED, calc_accuracy_loader, load_and_modify,
                           train_classifier_simple)

STRATEGIES = {
    "a": "새 헤드만",
    "b": "헤드+마지막블록+최종LN (교재)",
    "c": "전층",
}
MODELS = ["gpt2-small (124M)", "gpt2-medium (355M)"]

train_loader, val_loader, test_loader, *_ = build_loaders(batch_size=8)

rows = []
for model_name in MODELS:
    for strat in ("a", "b", "c"):
        tag = f"{model_name.split()[-1]} / ({strat}) {STRATEGIES[strat]}"
        print("=" * 74)
        print(tag)
        print("=" * 74)

        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()

        model, cfg = load_and_modify(model_name, strategy=strat, verbose=False)
        trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
        total = sum(p.numel() for p in model.parameters())
        print(f"  훈련 가능 {trainable:,} / 전체 {total:,} "
              f"({trainable/total*100:.2f}%)  헤드 in_features={cfg['emb_dim']}")

        torch.manual_seed(SEED)
        optimizer = torch.optim.AdamW(
            [p for p in model.parameters() if p.requires_grad],
            lr=5e-5, weight_decay=0.1)

        torch.cuda.synchronize()
        t0 = time.perf_counter()
        train_classifier_simple(model, train_loader, val_loader, optimizer,
                                device, num_epochs=5, eval_freq=1000,
                                eval_iter=5, use_bf16=True)
        torch.cuda.synchronize()
        elapsed = time.perf_counter() - t0

        test_acc = calc_accuracy_loader(test_loader, model, device)
        peak = torch.cuda.max_memory_allocated() / 1e9

        print(f"  → test 정확도 {test_acc*100:.2f}% / 총 {elapsed:.1f}초 "
              f"(에폭당 {elapsed/5:.1f}초) / 최대 메모리 {peak:.2f} GB")
        rows.append({
            "model": model_name.split()[-1].strip("()"),
            "strategy": strat,
            "label": STRATEGIES[strat],
            "trainable": trainable,
            "total": total,
            "epoch_sec": elapsed / 5,
            "peak_gb": peak,
            "test_acc": test_acc,
        })

        del model, optimizer
        torch.cuda.empty_cache()
        print()

# ---------------- 표 ----------------
print("=" * 74)
print("매트릭스 결과")
print("=" * 74)
hdr = f"{'조합':<34}{'훈련가능':>13}{'에폭당(s)':>11}{'최대GPU(GB)':>13}{'test':>9}"
print(hdr)
print("-" * len(hdr))
for r in rows:
    print(f"{r['model']} / ({r['strategy']}) {r['label']:<24}"[:34].ljust(34)
          + f"{r['trainable']:>13,}{r['epoch_sec']:>11.1f}"
          f"{r['peak_gb']:>13.2f}{r['test_acc']*100:>8.2f}%")

best_acc = max(rows, key=lambda r: r["test_acc"])
# 가성비 = 정확도 / 에폭당 시간
best_eff = max(rows, key=lambda r: r["test_acc"] / r["epoch_sec"])
print()
print(f"[검증 답] ① 정확도 최고: {best_eff and ''}"
      f"{best_acc['model']} / ({best_acc['strategy']}) {best_acc['label']} "
      f"— {best_acc['test_acc']*100:.2f}%")
print(f"[검증 답] ② 정확도/시간 가성비 최고: "
      f"{best_eff['model']} / ({best_eff['strategy']}) {best_eff['label']} "
      f"— {best_eff['test_acc']*100:.2f}% / 에폭당 {best_eff['epoch_sec']:.1f}초")

# ---------------- 리포트 ----------------
lines = ["# matrix_experiment.md — 동결 전략 × 모델 크기 매트릭스 (P11-6 산출물)", ""]
lines.append("공통: 시드 123 · 5 에폭 · AdamW lr=5e-5, weight_decay=0.1 · "
             "batch_size=8 · bf16 autocast · 조합마다 모델 완전 해제 후 "
             "`reset_peak_memory_stats()`")
lines.append("")
lines.append("| 조합 | 훈련 가능 파라미터 | 전체 대비 | 에폭당 시간(s) | 최대 GPU 메모리(GB) | test 정확도 |")
lines.append("|---|---|---|---|---|---|")
for r in rows:
    lines.append(f"| **{r['model']}** / ({r['strategy']}) {r['label']} | "
                 f"{r['trainable']:,} | {r['trainable']/r['total']*100:.2f}% | "
                 f"{r['epoch_sec']:.1f} | {r['peak_gb']:.2f} | "
                 f"**{r['test_acc']*100:.2f}%** |")
lines.append("")
lines.append("## 검증 답")
lines.append("")
lines.append(f"- **① 정확도가 가장 높은 조합**: {best_acc['model']} / "
             f"({best_acc['strategy']}) {best_acc['label']} — "
             f"test **{best_acc['test_acc']*100:.2f}%**")
lines.append(f"- **② 정확도/시간 가성비가 가장 좋은 조합**: {best_eff['model']} / "
             f"({best_eff['strategy']}) {best_eff['label']} — "
             f"test {best_eff['test_acc']*100:.2f}% 를 에폭당 "
             f"{best_eff['epoch_sec']:.1f}초에")
lines.append("")
lines.append("## 축별 읽기")
lines.append("")
by = {(r["model"], r["strategy"]): r for r in rows}
for m in ("124M)", "355M)"):
    key = m.strip(")")
    a, b, c = by[(key, "a")], by[(key, "b")], by[(key, "c")]
    lines.append(f"**{key} — 동결을 풀수록**: (a) {a['test_acc']*100:.2f}% → "
                 f"(b) {b['test_acc']*100:.2f}% → (c) {c['test_acc']*100:.2f}%. "
                 f"훈련 가능 파라미터는 {a['trainable']:,} → {b['trainable']:,} → "
                 f"{c['trainable']:,} 로 {c['trainable']/a['trainable']:.0f}배가 되고, "
                 f"에폭당 시간은 {a['epoch_sec']:.1f}s → {c['epoch_sec']:.1f}s "
                 f"({c['epoch_sec']/a['epoch_sec']:.1f}배), "
                 f"메모리는 {a['peak_gb']:.2f}GB → {c['peak_gb']:.2f}GB "
                 f"({c['peak_gb']/a['peak_gb']:.1f}배)다.")
    lines.append("")
for s in ("a", "b", "c"):
    s1, s2 = by[("124M", s)], by[("355M", s)]
    lines.append(f"**전략 ({s}) — 모델을 키우면**: 124M {s1['test_acc']*100:.2f}% → "
                 f"355M {s2['test_acc']*100:.2f}% "
                 f"({(s2['test_acc']-s1['test_acc'])*100:+.2f}%p). "
                 f"대신 에폭당 시간 {s2['epoch_sec']/s1['epoch_sec']:.1f}배, "
                 f"메모리 {s2['peak_gb']/s1['peak_gb']:.1f}배.")
    lines.append("")
lines.append("> **해석 과제**(어디까지 풀겠는가)는 report.md 에 학생이 직접 작성한다 — "
             "이번 주 채점 포인트이며 에이전트 사용 금지 항목이다.")

with open("matrix_experiment.md", "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
print("\n[저장] matrix_experiment.md")
