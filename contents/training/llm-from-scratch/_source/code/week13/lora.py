"""P13-4 — LoRA 구현과 풀 튜닝 대비 3축(시간·메모리·점수) 비교.

⚠️ 스케일 표기 주의: 교재 13.1 배경이론은 `출력 = W·x + (α/r)·B·A·x` 라 하고,
   실행 프롬프트 P13-4 1번은 `forward = alpha * (x @ A @ B)` 라 한다. 둘은 다르다
   (r=16, α=16 이면 α/r=1 vs α=16 — 16배 차이).
   여기서는 **실행 지시(P13-4)를 그대로 따른다** — 교재 저장소 부록 E 구현과도 일치한다.
"""
import math

import torch


class LoRALayer(torch.nn.Module):
    """저랭크 곁가지. B 를 0 으로 두어 초기 출력이 0 이 되게 한다."""

    def __init__(self, in_dim, out_dim, rank, alpha):
        super().__init__()
        self.A = torch.nn.Parameter(torch.empty(in_dim, rank))
        torch.nn.init.kaiming_uniform_(self.A, a=math.sqrt(5))
        self.B = torch.nn.Parameter(torch.zeros(rank, out_dim))
        self.alpha = alpha

    def forward(self, x):
        return self.alpha * (x @ self.A @ self.B)


class LinearWithLoRA(torch.nn.Module):
    """원본 Linear 출력 + LoRA 출력. 원본은 그대로 두고 곁가지만 더한다."""

    def __init__(self, linear, rank, alpha):
        super().__init__()
        self.linear = linear
        self.lora = LoRALayer(linear.in_features, linear.out_features, rank, alpha)

    def forward(self, x):
        return self.linear(x) + self.lora(x)


def replace_linear_with_lora(model, rank, alpha):
    """모델 안의 모든 nn.Linear 를 재귀적으로 LinearWithLoRA 로 교체한다."""
    for name, module in model.named_children():
        if isinstance(module, torch.nn.Linear):
            setattr(model, name, LinearWithLoRA(module, rank, alpha))
        else:
            replace_linear_with_lora(module, rank, alpha)
    return model


# ===========================================================================
if __name__ == "__main__":
    import json
    import statistics
    import time

    import common  # noqa: F401
    from common import (WEEK10_WEIGHTS, build_instruction_loaders, device,
                        text_to_token_ids, token_ids_to_text)

    import openai_load
    openai_load.WEIGHTS_DIR = WEEK10_WEIGHTS

    from decoding import generate                              # noqa: E402
    from instr_data import format_input                        # noqa: E402
    from judge import parse_score, query_model, score_prompt    # noqa: E402
    from pretrain import calc_loss_loader, train_model_simple   # noqa: E402

    before = json.load(open("before_tuning.json"))
    sft = json.load(open("sft_meta.json"))
    full_judge = json.load(open("judge_full.json"))

    (train_loader, val_loader, test_loader,
     train_data, val_data, test_data, tokenizer) = build_instruction_loaders(8)

    START = format_input(val_data[0])
    rows = []

    for rank, alpha in ((16, 16), (8, 16)):
        tag = f"LoRA r={rank}, α={alpha}"
        print("=" * 74)
        print(tag)
        print("=" * 74)

        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()

        # 4. 355M 새로 로드 → 전체 동결 → LoRA 교체 → LoRA 만 훈련 가능
        torch.manual_seed(123)
        model, cfg, _ = openai_load.build("gpt2-medium (355M)")
        base_total = sum(p.numel() for p in model.parameters())
        for p in model.parameters():
            p.requires_grad = False
        replace_linear_with_lora(model, rank=rank, alpha=alpha)
        model.to(device)

        trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
        total = sum(p.numel() for p in model.parameters())
        print(f"  원본 파라미터 {base_total:,} → LoRA 추가 후 {total:,}")
        print(f"  훈련 가능 **{trainable:,}** = 원본의 "
              f"**{trainable/base_total*100:.2f}%**")

        # 5. [훈련 전 게이트] B=0 이므로 원본과 손실이 같아야 한다
        model.eval()
        with torch.no_grad():
            va0 = calc_loss_loader(val_loader, model, device)
        gate = abs(va0 - before["val_loss"]) < 1e-4
        print(f"  [훈련 전 게이트] LoRA 적용 직후 val 손실 {va0:.6f} vs "
              f"원본 {before['val_loss']:.6f} → 차이 "
              f"{abs(va0-before['val_loss']):.2e}  **{'PASS' if gate else 'FAIL'}**")

        # 6. 2 에폭 튜닝
        optimizer = torch.optim.AdamW(
            [p for p in model.parameters() if p.requires_grad],
            lr=5e-5, weight_decay=0.1)
        torch.cuda.synchronize()
        t0 = time.perf_counter()
        train_model_simple(model, train_loader, val_loader, optimizer, device,
                           num_epochs=2, eval_freq=1000, eval_iter=5,
                           start_context=START, tokenizer=tokenizer)
        torch.cuda.synchronize()
        elapsed = time.perf_counter() - t0
        peak = torch.cuda.max_memory_allocated() / 1e9

        model.eval()
        with torch.no_grad():
            va = calc_loss_loader(val_loader, model, device)
        print(f"  훈련 {elapsed:.1f}초 / peak {peak:.2f} GB / 최종 val 손실 {va:.4f}")

        # 테스트 응답 생성
        resp_file = f"test_responses_lora_r{rank}.json"
        results = []
        for entry in test_data:
            prompt = format_input(entry)
            ids = text_to_token_ids(prompt, tokenizer).to(device)
            out = generate(model, ids, max_new_tokens=256,
                           context_size=cfg["context_length"],
                           temperature=0.0, eos_id=50256)
            tail = token_ids_to_text(out, tokenizer)[len(prompt):]
            r = tail.replace("### Response:", "").strip()
            for stop in ("### Instruction:", "### Input:", "### Response:"):
                if stop in r:
                    r = r.split(stop)[0].strip()
            results.append(dict(entry, model_response=r))
        json.dump(results, open(resp_file, "w"), ensure_ascii=False, indent=2)
        torch.save(model.state_dict(), f"lora_355m_r{rank}.pth")
        print(f"  [저장] {resp_file}, lora_355m_r{rank}.pth")

        # 저지 채점
        print(f"  저지 채점 중...", end="", flush=True)
        scores = []
        for i, e in enumerate(results, 1):
            v = parse_score(query_model(score_prompt(e, e["model_response"])))[0]
            if v is not None:
                scores.append(v)
            if i % 30 == 0:
                print(f" {i}", end="", flush=True)
        print()
        jm = statistics.mean(scores)
        print(f"  저지 평균 **{jm:.2f}점** (성공 {len(scores)}/110)")

        rows.append({
            "tag": tag, "rank": rank, "alpha": alpha,
            "trainable": trainable, "base_total": base_total,
            "ratio": trainable / base_total * 100,
            "elapsed": elapsed, "peak": peak, "val_loss": va,
            "judge_mean": jm, "gate": gate, "gate_loss": va0,
        })

        del model, optimizer
        torch.cuda.empty_cache()
        print()

    # ---------------- 비교표 ----------------
    print("=" * 74)
    print("3축 비교")
    print("=" * 74)
    hdr = (f"{'방식':<16}{'훈련가능':>14}{'비율':>8}{'시간(s)':>10}"
           f"{'peak(GB)':>10}{'val손실':>9}{'저지평균':>9}")
    print(hdr)
    print("-" * len(hdr))
    print(f"{'풀 튜닝':<16}{406_286_336:>14,}{100.0:>7.2f}%"
          f"{sft['elapsed_sec']:>10.1f}{sft['peak_gb']:>10.2f}"
          f"{sft['val_loss']:>9.4f}{full_judge['mean']:>9.2f}")
    for r in rows:
        print(f"{r['tag']:<16}{r['trainable']:>14,}{r['ratio']:>7.2f}%"
              f"{r['elapsed']:>10.1f}{r['peak']:>10.2f}"
              f"{r['val_loss']:>9.4f}{r['judge_mean']:>9.2f}")

    L = ["# lora_compare.md — LoRA vs 풀 튜닝 3축 비교 (P13-4 산출물)", ""]
    L.append("베이스: GPT-2 355M · 데이터: 지시 데이터 935건 · 2 에폭 · "
             "AdamW lr=5e-5 wd=0.1 · batch_size=8 · 시드 123")
    L.append("")
    L.append("| 방식 | 훈련 가능 파라미터 | 원본 대비 | 시간(s) | peak 메모리(GB) | 최종 val 손실 | 저지 평균 |")
    L.append("|---|---|---|---|---|---|---|")
    L.append(f"| **풀 튜닝** | 406,286,336 | 100.00% | {sft['elapsed_sec']:.1f} | "
             f"{sft['peak_gb']:.2f} | {sft['val_loss']:.4f} | "
             f"**{full_judge['mean']:.2f}** |")
    for r in rows:
        L.append(f"| **{r['tag']}** | {r['trainable']:,} | {r['ratio']:.2f}% | "
                 f"{r['elapsed']:.1f} | {r['peak']:.2f} | {r['val_loss']:.4f} | "
                 f"**{r['judge_mean']:.2f}** |")
    L.append("")
    L.append("## 훈련 전 게이트 (B=0 초기화)")
    L.append("")
    L.append("| 설정 | LoRA 적용 직후 val 손실 | 원본(P13-0) val 손실 | 차이 | 판정 |")
    L.append("|---|---|---|---|---|")
    for r in rows:
        L.append(f"| {r['tag']} | {r['gate_loss']:.6f} | {before['val_loss']:.6f} | "
                 f"{abs(r['gate_loss']-before['val_loss']):.2e} | "
                 f"**{'PASS' if r['gate'] else 'FAIL'}** |")
    L.append("")
    L.append("B 가 0 이므로 `alpha * (x @ A @ B)` 가 항상 0 이고, "
             "`linear(x) + 0 = linear(x)` 다. 훈련 시작 시점의 모델은 원본과 "
             "**비트 단위로 같다** — 안전한 출발점이자 구현이 맞았는지 확인하는 게이트다. "
             "10주차 '이식 품질 게이트'와 같은 사상이다.")
    L.append("")
    L.append("## 축별 읽기")
    L.append("")
    r16 = rows[0]
    L.append(f"- **파라미터**: 406,286,336 → {r16['trainable']:,} "
             f"({r16['ratio']:.2f}%). {100/r16['ratio']:.0f}배 감소.")
    L.append(f"- **메모리**: {sft['peak_gb']:.2f}GB → {r16['peak']:.2f}GB "
             f"({sft['peak_gb']/r16['peak']:.2f}배 절감). "
             f"AdamW 의 모멘트 2개가 곁가지에만 붙기 때문이다 "
             f"(9주차 메모리 해부의 응용).")
    L.append(f"- **시간**: {sft['elapsed_sec']:.1f}s → {r16['elapsed']:.1f}s "
             f"({sft['elapsed_sec']/r16['elapsed']:.2f}배). "
             f"역전파는 여전히 전 층을 통과해야 하므로 파라미터 수만큼 줄지는 않는다.")
    L.append(f"- **점수**: 풀 {full_judge['mean']:.2f} vs r16 {r16['judge_mean']:.2f} "
             f"({r16['judge_mean']-full_judge['mean']:+.2f}점).")
    L.append("")
    L.append("> **해석 과제(본인 작성)**: 위 3축을 근거로 "
             "\"언제 LoRA 를 쓰고 언제 풀 튜닝을 쓸 것인가\"에 대한 자기 기준을 "
             "3~5문장으로 세워라. 14주차 프로젝트에서 이 기준을 실제로 쓰게 된다.")
    L.append("")
    L.append("⚠️ **저지 점수 비교 시 주의**: V13-1 심화 검증에서 같은 응답 110개를 "
             "두 번 채점했을 때 개별 점수가 **8.2%(9건)** 달라졌다(평균 변동 폭 31점). "
             "다만 **평균은 60.92 → 60.71 로 0.21점만 움직였다.** "
             "따라서 위 표의 저지 평균은 **±1점 수준의 차이를 유의미하게 볼 수 없다.**")

    with open("lora_compare.md", "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    json.dump(rows, open("lora_meta.json", "w"), ensure_ascii=False, indent=2)
    print("\n[저장] lora_compare.md, lora_meta.json")
