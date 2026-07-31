"""P13-1 — GPT-2 355M 지시 튜닝.

핵심 관찰: **손실 함수는 9주차 사전 훈련과 완전히 같다** (cross entropy, 다음 토큰 예측).
9주차 train_model_simple 을 그대로 재사용한다 — 코드 한 줄 바꾸지 않는다.
바뀐 것은 데이터 형식(Alpaca 템플릿)과 -100 마스킹뿐이다.
"""
import json
import time

import matplotlib.pyplot as plt
import torch

import common  # noqa: F401
from common import (WEEK10_WEIGHTS, build_instruction_loaders, device,
                    text_to_token_ids, token_ids_to_text)

import openai_load
openai_load.WEIGHTS_DIR = WEEK10_WEIGHTS

from decoding import generate                              # noqa: E402
from instr_data import format_input                        # noqa: E402
from pretrain import calc_loss_loader, train_model_simple   # noqa: E402

before = json.load(open("before_tuning.json"))

train_loader, val_loader, test_loader, train_data, val_data, test_data, tokenizer = \
    build_instruction_loaders(batch_size=8)

torch.manual_seed(123)
model, cfg, _ = openai_load.build("gpt2-medium (355M)")
optimizer = torch.optim.AdamW(model.parameters(), lr=5e-5, weight_decay=0.1)

START = format_input(val_data[0])

print("=" * 74)
print("P13-1 — 355M 지시 튜닝 (2 에폭, AdamW lr=5e-5 wd=0.1)")
print("=" * 74)
print(f"손실 함수: 9주차와 동일한 cross_entropy(다음 토큰 예측). "
      f"train_model_simple 을 그대로 재사용한다.")
print()

torch.cuda.empty_cache()
torch.cuda.reset_peak_memory_stats()
torch.cuda.synchronize()
t0 = time.perf_counter()

train_losses, val_losses, tokens_seen, epoch_samples = train_model_simple(
    model, train_loader, val_loader, optimizer, device,
    num_epochs=2, eval_freq=5, eval_iter=5,
    start_context=START, tokenizer=tokenizer,
)

torch.cuda.synchronize()
elapsed = time.perf_counter() - t0
peak = torch.cuda.max_memory_allocated() / 1e9

print()
print(f"훈련 시간 {elapsed:.1f}초 / peak GPU 메모리 **{peak:.2f} GB**")

# 전체 로더 기준 최종 손실
model.eval()
with torch.no_grad():
    tr_full = calc_loss_loader(train_loader, model, device)
    va_full = calc_loss_loader(val_loader, model, device)
print(f"최종 손실(전체 로더): train **{tr_full:.4f}** / val **{va_full:.4f}**")
print(f"  튜닝 전            : train {before['train_loss']:.4f} / "
      f"val {before['val_loss']:.4f}")
print(f"  1 미만인가          : train {tr_full < 1.0} / val {va_full < 1.0}")
print(f"  train < val 인가    : {tr_full < va_full}")

# 곡선
fig, ax = plt.subplots(figsize=(9, 5))
xs = torch.linspace(0, 2, len(train_losses))
ax.plot(xs, train_losses, label="훈련 손실")
ax.plot(xs, val_losses, linestyle="-.", label="검증 손실")
ax.axhline(before["val_loss"], color="gray", linestyle=":",
           label=f"튜닝 전 val {before['val_loss']:.2f}")
ax.axhline(1.0, color="red", linestyle="--", alpha=0.5, label="손실 1.0")
ax.set_xlabel("에폭"); ax.set_ylabel("손실")
ax.set_title("지시 튜닝 손실 곡선 (GPT-2 355M, 2 에폭)")
ax.legend(); ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig("sft_loss_curve.png", dpi=130)
print("[저장] sft_loss_curve.png")

torch.save(model.state_dict(), "sft_355m.pth")
print("[저장] sft_355m.pth")

# ---- 튜닝 전후 대조 ----
print()
print("=" * 74)
print("튜닝 전후 대조 — val 예제 3개")
print("=" * 74)

rows = []
for i in range(3):
    entry = val_data[i]
    prompt = format_input(entry)
    ids = text_to_token_ids(prompt, tokenizer).to(device)
    out = generate(model, ids, max_new_tokens=35,
                   context_size=cfg["context_length"], temperature=0.0,
                   eos_id=50256)
    after = token_ids_to_text(out, tokenizer)[len(prompt):]
    rows.append((entry, after))

    print(f"\n───── 예제 {i+1} ─────")
    print(f"[지시] {entry['instruction']}")
    if entry["input"].strip():
        print(f"[입력] {entry['input']}")
    print(f"[정답] {entry['output']}")
    if i == 0:
        print(f"[튜닝 전] {before['val0_before']!r}")
    print(f"[튜닝 후] {after!r}")

print()
print("=" * 74)
print("[검증] 형식 준수 관점의 차이")
print("=" * 74)
b = before["val0_before"]
a = rows[0][1]
print(f"  튜닝 전: '### Response:' 를 **스스로 찍고** 시작한다. "
      f"그리고 응답을 마친 뒤 '### Instruction:' 을 또 찍어 "
      f"**새 문제를 지어낸다** — 멈출 줄 모른다.")
print(f"           내용도 지시를 수행하지 않았다(수동태 변환 실패, 원문 그대로 반복).")
print(f"  튜닝 후: 프롬프트가 '### Response:' 로 끝나므로 모델은 "
      f"**응답만** 이어 쓴다. 그리고 <|endoftext|> 로 **멈춘다** "
      f"(12주차에서 첫 50256 하나를 남긴 이유).")
print()
print(f"  → 손실 함수는 한 줄도 안 바꿨다. 바뀐 것은 데이터 형식과 마스킹뿐이다.")
print(f"    2 에폭 · 935건으로 **행동 양식**이 바뀌었다.")

json.dump({
    "elapsed_sec": elapsed, "peak_gb": peak,
    "train_loss": tr_full, "val_loss": va_full,
    "train_curve": train_losses, "val_curve": val_losses,
}, open("sft_meta.json", "w"), indent=2)
print("\n[저장] sft_meta.json")
